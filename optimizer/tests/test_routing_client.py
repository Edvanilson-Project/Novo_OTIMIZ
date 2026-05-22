import pytest
from unittest.mock import MagicMock, patch
from src.infrastructure.routing_client import RoutingClient

@pytest.fixture
def mock_redis():
    with patch('redis.from_url') as mock:
        yield mock

@pytest.fixture
def mock_requests():
    with patch('requests.get') as mock:
        yield mock

def test_routing_cache_hit(mock_redis):
    # Setup mock redis para retornar valor no GET
    client_mock = MagicMock()
    client_mock.get.return_value = '{"distance_km": 10.5, "duration_min": 20.0}'
    mock_redis.return_value = client_mock
    
    # Reset Singleton para teste
    RoutingClient._instance = None
    routing = RoutingClient()
    
    dist, dur = routing.get_route(-23.5, -46.6, -23.6, -46.7, origin_id=1, destination_id=2)
    
    assert dist == 10.5
    assert dur == 20.0
    client_mock.get.assert_called_with("route:1:2")

def test_routing_osrm_call_and_cache_save(mock_redis, mock_requests):
    # Setup redis para retornar cache miss e requests para sucesso
    redis_mock = MagicMock()
    redis_mock.get.return_value = None
    mock_redis.return_value = redis_mock
    
    req_mock = MagicMock()
    req_mock.status_code = 200
    req_mock.json.return_value = {
        "code": "Ok",
        "routes": [{"distance": 5000, "duration": 600}]
    }
    mock_requests.return_value = req_mock
    
    RoutingClient._instance = None
    routing = RoutingClient()
    
    dist, dur = routing.get_route(-23.5, -46.6, -23.55, -46.65, origin_id=10, destination_id=20)
    
    assert dist == 5.0  # 5000m -> 5km
    assert dur == 10.0 # 600s -> 10min
    
    # Verificar se salvou no cache
    redis_mock.setex.assert_called()

def test_routing_haversine_fallback(mock_redis, mock_requests):
    # Setup redis miss e requests erro
    redis_mock = MagicMock()
    redis_mock.get.return_value = None
    mock_redis.return_value = redis_mock

    mock_requests.side_effect = Exception("OSRM Down")

    RoutingClient._instance = None
    routing = RoutingClient()

    # São Paulo -> Rio (aprox 350-400km)
    dist, dur = routing.get_route(-23.55, -46.63, -22.90, -43.17)

    assert dist > 300.0
    assert dur > 0  # Deve calcular algum tempo


# ─────────────────────────────────────────────────────────────────────────────
# Regressão: chaves de cache devem ser determinísticas (sem componente temporal)
# Invariante documentado em CLAUDE.md raiz: "Never include time-based components
# (e.g., time.time() // 3600) in cache keys — defeats TTL-based expiry."
# ─────────────────────────────────────────────────────────────────────────────

def test_matrix_cache_key_deterministic_across_calls(mock_redis):
    """_matrix_cache_key deve gerar a mesma chave em chamadas sucessivas."""
    redis_mock = MagicMock()
    mock_redis.return_value = redis_mock

    RoutingClient._instance = None
    routing = RoutingClient()

    location_ids = [10, 20, 30]
    k1 = routing._matrix_cache_key(location_ids)
    k2 = routing._matrix_cache_key(location_ids)
    assert k1 == k2, "matrix_cache_key não é determinística entre chamadas"


def test_matrix_cache_key_stable_across_time(mock_redis):
    """Mesmos inputs em janelas de tempo diferentes ⇒ mesma chave (TTL faz expiry)."""
    redis_mock = MagicMock()
    mock_redis.return_value = redis_mock

    RoutingClient._instance = None
    routing = RoutingClient()

    location_ids = [1, 2, 3, 4, 5]
    k_now = routing._matrix_cache_key(location_ids)

    # Simula passagem de tempo (qualquer time.time() injetado não pode mudar a chave)
    with patch("time.time", return_value=99999999.0):
        k_future = routing._matrix_cache_key(location_ids)

    assert k_now == k_future, "matrix_cache_key mudou com time.time() — TTL será defeitado"


def test_cost_params_hash_deterministic(mock_redis):
    """_get_cost_params_hash não pode depender de time.time (defeat TTL)."""
    redis_mock = MagicMock()
    mock_redis.return_value = redis_mock

    RoutingClient._instance = None
    routing = RoutingClient()
    # Para o hash dar resultado consistente, injeta evaluator estável
    routing.evaluator = MagicMock()
    routing.evaluator.crew_cost_per_hour = 25.0
    routing.evaluator.cost_km = 2.5

    h1 = routing._get_cost_params_hash()
    with patch("time.time", return_value=99999999.0):
        h2 = routing._get_cost_params_hash()
    assert h1 == h2, "cost_params_hash mudou com time.time() — quebra reprodutibilidade do cache"
