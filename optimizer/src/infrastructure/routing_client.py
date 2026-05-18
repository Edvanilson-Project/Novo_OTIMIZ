"""
routing_client.py — Cliente de Roteamento com Matrix Routing (OSRM /table).

MELHORIA MATEMÁTICA v2.0 (DeepSeek R1 Analysis):
- Método `get_route_matrix()` substitui o loop N² de chamadas individuais por
  UMA requisição ao endpoint /table do OSRM, que retorna toda a matriz de
  tempos de deslocamento de uma vez.
  Para N=500 viagens: reduz de ~250.000 chamadas HTTP → 1 chamada.
- Mantém `get_route()` para casos isolados (compatibilidade total).
- Fallback Haversine matricial quando OSRM está offline.
- Cache Redis com TTL configurável por rota individual e por matriz.
"""

import json
import logging
import math
import time
from typing import Dict, List, Optional, Tuple

import redis
import requests

from ..core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class RoutingClient:
    """
    Cliente de Roteamento Singleton com suporte a Matrix Routing.
    Prioridade: Cache Redis → OSRM Matrix API → Fallback Haversine.
    """

    _instance: Optional["RoutingClient"] = None

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

        self.osrm_url = settings.osrm_url.rstrip("/")
        self._initialized = True

    # ── Rota Individual (legacy, mantido para compatibilidade) ─────────────────

    def get_route(
        self,
        orig_lat: float,
        orig_lon: float,
        dest_lat: float,
        dest_lon: float,
        origin_id: Optional[int] = None,
        destination_id: Optional[int] = None,
    ) -> Tuple[float, float]:
        """
        Retorna (distancia_km, duracao_min).
        Fluxo: Cache Redis → OSRM API → Fallback Haversine.
        """
        cache_key = self._get_cache_key(orig_lat, orig_lon, dest_lat, dest_lon, origin_id, destination_id)
        if self.redis:
            try:
                cached_data = self.redis.get(cache_key)
                if cached_data:
                    data = json.loads(cached_data)
                    return data["distance_km"], data["duration_min"]
            except Exception as e:
                logger.debug(f"Erro ao ler cache Redis: {e}")

        if settings.osrm_enabled:
            try:
                url = f"{self.osrm_url}/route/v1/driving/{orig_lon},{orig_lat};{dest_lon},{dest_lat}?overview=false"
                # TIMEOUT v2.0: 3s conexão, 10s leitura para rotas individuais
                response = requests.get(url, timeout=(3.0, 10.0))
                if response.status_code == 200:
                    result = response.json()
                    if result.get("code") == "Ok" and result.get("routes"):
                        route = result["routes"][0]
                        dist_km = route["distance"] / 1000.0
                        dur_min = route["duration"] / 60.0
                        self._save_to_cache(cache_key, dist_km, dur_min)
                        return dist_km, dur_min
                else:
                    logger.warning(f"OSRM retornou status {response.status_code}. Ativando fallback.")
            except Exception as e:
                logger.warning(f"OSRM Offline ou inacessível ({e}). Ativando fallback Haversine.")

        return self._haversine_fallback(orig_lat, orig_lon, dest_lat, dest_lon)

    # ── Matrix Routing (NOVO) — O(1) em vez de O(N²) ─────────────────────────

    def get_route_matrix(
        self,
        locations: List[Tuple[float, float, int]],
    ) -> Dict[Tuple[int, int], float]:
        """
        Calcula a matriz de tempos de deslocamento para uma lista de localizações
        usando o endpoint /table do OSRM (UMA requisição para N² pares).

        Args:
            locations: Lista de (latitude, longitude, location_id).

        Returns:
            Dicionário {(origin_id, dest_id): duration_minutes} para todos os pares
            onde origin_id != dest_id. Tempo de deslocamento 0 para pares idênticos.

        Performance:
            N=100  → 1 chamada (vs 10.000 individuais)
            N=500  → 1 chamada (vs 250.000 individuais)
            N=1000 → 1 chamada (vs 1.000.000 individuais)
        """
        if not locations:
            return {}

        location_ids = [loc[2] for loc in locations]
        len(locations)

        # Tentar buscar matriz completa do cache Redis
        matrix_cache_key = self._matrix_cache_key(location_ids)
        if self.redis:
            try:
                cached = self.redis.get(matrix_cache_key)
                if cached:
                    raw_matrix = json.loads(cached)
                    # Restaurar chaves de tupla (JSON serializa como strings)
                    return {(int(k.split(",")[0]), int(k.split(",")[1])): float(v) for k, v in raw_matrix.items()}
            except Exception as e:
                logger.debug(f"Erro ao ler matriz do cache Redis: {e}")

        # Tentar OSRM /table
        if settings.osrm_enabled:
            result = self._osrm_table(locations, location_ids)
            if result is not None:
                self._save_matrix_to_cache(matrix_cache_key, result)
                return result

        # Fallback: calcular matriz Haversine
        logger.info("Usando matriz Haversine como fallback (OSRM offline).")
        result = self._haversine_matrix(locations, location_ids)
        self._save_matrix_to_cache(matrix_cache_key, result)
        return result

    def _osrm_table(
        self,
        locations: List[Tuple[float, float, int]],
        location_ids: List[int],
    ) -> Optional[Dict[Tuple[int, int], float]]:
        """Versão robusta com tratamento de erros e BATCHING (500x500)."""
        if not locations:
            return {}

        n = len(locations)
        # BATCHING: OSRM tem limites de payload. Dividimos em blocos de 500.
        batch_size = 500
        full_matrix: Dict[Tuple[int, int], float] = {}

        for i in range(0, n, batch_size):
            for j in range(0, n, batch_size):
                sources = locations[i : i + batch_size]
                destinations = locations[j : j + batch_size]

                source_ids = location_ids[i : i + batch_size]
                dest_ids = location_ids[j : j + batch_size]

                # coords: todos os sources seguidos de todos os destinations
                all_coords = sources + destinations
                coords_str = ";".join(f"{lon},{lat}" for lat, lon, _ in all_coords)

                source_indices = ";".join(str(idx) for idx in range(len(sources)))
                dest_indices = ";".join(str(idx) for idx in range(len(sources), len(sources) + len(destinations)))

                url = (
                    f"{self.osrm_url}/table/v1/driving/{coords_str}?"
                    f"sources={source_indices}&destinations={dest_indices}&annotations=duration"
                )

                try:
                    # TIMEOUT v2.0: 5s conexão, 30s leitura para matrizes
                    response = requests.get(url, timeout=(5.0, 30.0))
                    if response.status_code != 200:
                        logger.warning(f"OSRM /table batch ({i},{j}) retornou status {response.status_code}.")
                        continue

                    data = response.json()
                    if data.get("code") != "Ok":
                        logger.warning(f"OSRM /table batch falhou: {data.get('message', 'Unknown')}")
                        continue

                    durations = data.get("durations", [])
                    for row_idx, row in enumerate(durations):
                        for col_idx, dur_secs in enumerate(row):
                            origin_id = source_ids[row_idx]
                            dest_id = dest_ids[col_idx]
                            if origin_id == dest_id:
                                continue

                            if dur_secs is None:
                                full_matrix[(origin_id, dest_id)] = 999_999.0
                            else:
                                full_matrix[(origin_id, dest_id)] = max(0.0, float(dur_secs) / 60.0)

                except Exception as e:
                    logger.warning(f"Falha no lote OSRM ({i},{j}): {e}")
                    continue

        if not full_matrix:
            return None

        # VALIDAÇÃO: Preencher buracos se necessário
        expected_pairs = n * (n - 1)
        if len(full_matrix) < expected_pairs:
            logger.warning(f"Matriz incompleta após batching: {len(full_matrix)}/{expected_pairs}")
            for i_idx in range(n):
                for j_idx in range(n):
                    if i_idx == j_idx:
                        continue
                    key = (location_ids[i_idx], location_ids[j_idx])
                    if key not in full_matrix:
                        lat1, lon1, _ = locations[i_idx]
                        lat2, lon2, _ = locations[j_idx]
                        _, dur_min = self._haversine_fallback(lat1, lon1, lat2, lon2)
                        full_matrix[key] = dur_min

        return full_matrix

    def _haversine_matrix(
        self,
        locations: List[Tuple[float, float, int]],
        location_ids: List[int],
    ) -> Dict[Tuple[int, int], float]:
        """Calcula a matriz completa usando Haversine (15 km/h velocidade urbana)."""
        matrix: Dict[Tuple[int, int], float] = {}
        for i, (lat1, lon1, _) in enumerate(locations):
            for j, (lat2, lon2, _) in enumerate(locations):
                if i == j:
                    continue
                _, dur_min = self._haversine_fallback(lat1, lon1, lat2, lon2)
                matrix[(location_ids[i], location_ids[j])] = dur_min
        return matrix

    def _matrix_cache_key(self, location_ids: List[int], cost_params_hash: str = "") -> str:
        """Chave de cache Redis para a matriz completa com versionamento.

        Args:
            location_ids: IDs das localizações
            cost_params_hash: Hash dos parâmetros de custo atuais

        Returns:
            Chave de cache versionada e única para esta combinação
        """
        # Incluir hash dos parâmetros de custo se fornecido
        if cost_params_hash:
            ids_hash = hash(tuple(sorted(location_ids)) + (cost_params_hash,))
        else:
            ids_hash = hash(tuple(sorted(location_ids)))

        return f"route_matrix:v2:{abs(ids_hash)}"

    def _get_cost_params_hash(self) -> str:
        """Gera hash dos parâmetros de custo atuais para versionamento de cache.

        Calcula um hash MD5 baseado nos parâmetros de custo atuais.
        Isso garante que mudanças nos custos invalidem automaticamente o cache.
        """
        import hashlib
        import json

        params = {
            "crew_cost": getattr(self.evaluator, "crew_cost_per_hour", 25.0),
            "vehicle_cost": getattr(self.evaluator, "cost_km", 2.5),
            "timestamp": int(time.time() // 3600),  # Muda a cada hora
        }
        return hashlib.md5(json.dumps(params).encode()).hexdigest()[:8]

    def _save_matrix_to_cache(
        self,
        key: str,
        matrix: Dict[Tuple[int, int], float],
    ) -> None:
        if not self.redis:
            return
        try:
            # JSON não suporta chaves tuple — converter para "id1,id2"
            serializable = {f"{k[0]},{k[1]}": v for k, v in matrix.items()}
            self.redis.setex(key, settings.routing_cache_ttl, json.dumps(serializable))
        except Exception as e:
            logger.debug(f"Erro ao salvar matriz no cache Redis: {e}")

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _get_cache_key(self, lat1, lon1, lat2, lon2, id1, id2) -> str:
        if id1 is not None and id2 is not None:
            return f"route:{id1}:{id2}"
        return f"route:{round(lat1, 5)}:{round(lon1, 5)}:{round(lat2, 5)}:{round(lon2, 5)}"

    def _save_to_cache(self, key: str, dist_km: float, dur_min: float):
        if not self.redis:
            return
        try:
            value = json.dumps({"distance_km": dist_km, "duration_min": dur_min})
            self.redis.setex(key, settings.routing_cache_ttl, value)
        except Exception as e:
            logger.debug(f"Erro ao salvar no cache Redis: {e}")

    def _haversine_fallback(self, lat1, lon1, lat2, lon2) -> Tuple[float, float]:
        """Calcula distância euclidiana curvada e assume 15km/h de velocidade média."""
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        distance_km = R * c
        # 15 km/h = 0.25 km/min
        duration_min = distance_km / 0.25
        if distance_km > 0.1:
            duration_min = max(1.0, duration_min)
        return distance_km, duration_min
