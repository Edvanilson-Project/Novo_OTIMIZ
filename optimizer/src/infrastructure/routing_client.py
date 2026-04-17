import json
import logging
import math
import time
from typing import Optional, Tuple

import redis
import requests

from ..core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class RoutingClient:
    """
    Cliente de Roteamento Singleton.
    Gerencia cache no Redis, chamadas OSRM e fallback Haversine.
    """
    _instance: Optional['RoutingClient'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RoutingClient, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        try:
            self.redis = redis.from_url(settings.redis_url, decode_responses=True)
            self.redis.ping()
            logger.info("Conectado ao Redis para cache de roteamento.")
        except Exception as e:
            logger.warning(f"Falha ao conectar no Redis. O cache de roteamento será desativado. Erro: {e}")
            self.redis = None

        self.osrm_url = settings.osrm_url.rstrip('/')
        self._initialized = True

    def get_route(
        self,
        orig_lat: float,
        orig_lon: float,
        dest_lat: float,
        dest_lon: float,
        origin_id: Optional[int] = None,
        destination_id: Optional[int] = None
    ) -> Tuple[float, float]:
        """
        Retorna (distancia_km, duracao_min).
        Fluxo: Cache Redis -> OSRM API -> Fallback Haversine.
        """
        # 1. Tentar Cache
        cache_key = self._get_cache_key(orig_lat, orig_lon, dest_lat, dest_lon, origin_id, destination_id)
        if self.redis:
            try:
                cached_data = self.redis.get(cache_key)
                if cached_data:
                    data = json.loads(cached_data)
                    return data['distance_km'], data['duration_min']
            except Exception as e:
                logger.debug(f"Erro ao ler cache Redis: {e}")

        # 2. Tentar OSRM
        if settings.osrm_enabled:
            try:
                url = f"{self.osrm_url}/route/v1/driving/{orig_lon},{orig_lat};{dest_lon},{dest_lat}?overview=false"
                response = requests.get(url, timeout=2.0)
                if response.status_code == 200:
                    result = response.json()
                    if result.get('code') == 'Ok' and result.get('routes'):
                        route = result['routes'][0]
                        dist_km = route['distance'] / 1000.0
                        dur_min = route['duration'] / 60.0
                        
                        self._save_to_cache(cache_key, dist_km, dur_min)
                        return dist_km, dur_min
                else:
                    logger.warning(f"OSRM retornou status {response.status_code}. Ativando fallback.")
            except Exception as e:
                logger.warning(f"OSRM Offline ou inacessível ({e}). Ativando fallback Haversine.")

        # 3. Fallback Haversine (15 km/h velocidade urbana média)
        return self._haversine_fallback(orig_lat, orig_lon, dest_lat, dest_lon)

    def _get_cache_key(self, lat1, lon1, lat2, lon2, id1, id2) -> str:
        if id1 is not None and id2 is not None:
            return f"route:{id1}:{id2}"
        # Se não houver IDs, usa as coordenadas arredondadas como chave
        return f"route:{round(lat1, 5)}:{round(lon1, 5)}:{round(lat2, 5)}:{round(lon2, 5)}"

    def _save_to_cache(self, key: str, dist_km: float, dur_min: float):
        if not self.redis:
            return
        try:
            value = json.dumps({'distance_km': dist_km, 'duration_min': dur_min})
            self.redis.setex(key, settings.routing_cache_ttl, value)
        except Exception as e:
            logger.debug(f"Erro ao salvar no cache Redis: {e}")

    def _haversine_fallback(self, lat1, lon1, lat2, lon2) -> Tuple[float, float]:
        """Calcula distância euclidiana curvada e assume 15km/h de velocidade média."""
        R = 6371.0  # Raio da Terra em km
        
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        
        a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        distance_km = R * c
        
        # 15 km/h = 0.25 km/min
        duration_min = distance_km / 0.25
        
        # Garantir mínimo de 1 minuto para qualquer deslocamento
        if distance_km > 0.1:
            duration_min = max(1.0, duration_min)
            
        return distance_km, duration_min
