"""
Hierarquia de exceções do OTIMIZ Optimizer.
"""


class OptimizerError(Exception):
    """Exceção raiz do microserviço."""

    def __init__(self, message: str, code: str = "OPTIMIZER_ERROR", details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


class InfeasibleProblemError(OptimizerError):
    """O problema é inviável (e.g., sem viagens na linha)."""

    def __init__(self, message: str = "Problem is infeasible", details: dict | None = None):
        super().__init__(message, code="INFEASIBLE_PROBLEM", details=details)


class AlgorithmTimeoutError(OptimizerError):
    """O algoritmo estourou o orçamento de tempo."""

    def __init__(self, algorithm: str, limit_s: float, details: dict | None = None):
        super().__init__(
            f"Algorithm '{algorithm}' exceeded time limit of {limit_s}s",
            code="ALGORITHM_TIMEOUT",
            details=details,
        )
        self.algorithm = algorithm
        self.limit_s = limit_s


class NoProblemDataError(OptimizerError):
    """Nenhum dado de problema enviado ou encontrado no DB."""

    def __init__(self, message: str = "No problem data available", details: dict | None = None):
        super().__init__(message, code="NO_PROBLEM_DATA", details=details)


class ILPSolverError(OptimizerError):
    """Erro no solver ILP (PuLP / CBC)."""

    def __init__(self, status: str, details: dict | None = None):
        super().__init__(
            f"ILP solver returned infeasible/unbounded status: {status}",
            code="ILP_SOLVER_ERROR",
            details=details,
        )
        self.status = status


class InvalidAlgorithmError(OptimizerError):
    """Nome de algoritmo desconhecido."""

    def __init__(self, name: str, details: dict | None = None):
        super().__init__(
            f"Unknown algorithm: '{name}'",
            code="INVALID_ALGORITHM",
            details=details,
        )
        self.name = name


class HardConstraintViolationError(OptimizerError):
    """Uma ou mais hard constraints fatais foram violadas."""

    def __init__(self, issues: list[str], details: dict | None = None):
        preview = "; ".join(issues[:5]) if issues else "unknown"
        suffix = "" if len(issues) <= 5 else f" (+{len(issues) - 5} adicionais)"
        super().__init__(
            f"Hard constraints violated: {preview}{suffix}",
            code="HARD_CONSTRAINT_VIOLATION",
            details=details,
        )
        self.issues = issues
