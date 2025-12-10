"""
GPU-aware Ray Workers for LLM Inference

This module provides Ray remote actors that run LLM inference on specific GPUs,
enabling true parallel LLM inference across multiple GPUs.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import ray
    RAY_AVAILABLE = True
except ImportError:
    RAY_AVAILABLE = False
    ray = None


def create_gpu_llm_workers(
    num_gpus: int,
    endpoints: list[str],
    model_name: str,
    temperature: float = 0.0,
    top_p: float = 0.1,
    max_tokens: int = 20000
):
    """
    Create GPU-aware LLM workers using Ray.

    Args:
        num_gpus: Number of GPUs to use
        endpoints: List of vLLM endpoints (one per GPU)
        model_name: Model name
        temperature: Default temperature
        top_p: Default top_p
        max_tokens: Default max_tokens

    Returns:
        List of Ray actor handles, one per GPU
    """
    if not RAY_AVAILABLE:
        raise RuntimeError("Ray is not available. Install with: pip install ray")

    # Ensure Ray is initialized
    if not ray.is_initialized():
        ray.init(ignore_reinit_error=True)

    # Create worker class with GPU assignment
    @ray.remote(num_gpus=0)  # Don't allocate GPU to the actor itself (vLLM already using it)
    class LLMWorker:
        """Ray actor for LLM inference on a specific GPU"""

        def __init__(self, gpu_id: int, endpoint: str, model_name: str,
                     temperature: float, top_p: float, max_tokens: int):
            """Initialize LLM worker

            Args:
                gpu_id: GPU ID for this worker (for logging)
                endpoint: vLLM endpoint URL
                model_name: Model name
                temperature: Default temperature
                top_p: Default top_p
                max_tokens: Default max_tokens
            """
            self.gpu_id = gpu_id
            self.endpoint = endpoint
            self.model_name = model_name
            self.temperature = temperature
            self.top_p = top_p
            self.max_tokens = max_tokens

            # Import and create LLM client in the worker process
            from pro_v.utils.llm_client import VLLMLLMClient
            self.client = VLLMLLMClient(
                endpoints=[endpoint],
                model_name=model_name,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens
            )

            logger.info(f"LLMWorker initialized on GPU {gpu_id} with endpoint {endpoint}")

        def chat(self, system: str, user: str,
                temperature: Optional[float] = None,
                top_p: Optional[float] = None,
                max_tokens: Optional[int] = None) -> str:
            """Execute chat request"""
            return self.client.chat(
                system=system,
                user=user,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens
            )

        def complete(self, prompt: str,
                    temperature: Optional[float] = None,
                    top_p: Optional[float] = None,
                    max_tokens: Optional[int] = None) -> str:
            """Execute completion request"""
            return self.client.complete(
                prompt=prompt,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens
            )

        def get_gpu_id(self) -> int:
            """Get GPU ID for this worker"""
            return self.gpu_id

    # Create workers
    workers = []
    for gpu_id in range(num_gpus):
        # Use endpoint corresponding to this GPU
        endpoint = endpoints[gpu_id % len(endpoints)]

        worker = LLMWorker.remote(
            gpu_id=gpu_id,
            endpoint=endpoint,
            model_name=model_name,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens
        )
        workers.append(worker)
        logger.info(f"Created LLM worker {gpu_id} for endpoint {endpoint}")

    return workers


class RoundRobinLLMClient:
    """
    LLM Client that distributes requests across multiple GPU workers using round-robin.

    This provides the same interface as VLLMLLMClient but uses Ray workers internally.
    """

    def __init__(self, workers: list):
        """
        Initialize round-robin LLM client

        Args:
            workers: List of Ray LLM worker actors
        """
        self.workers = workers
        self.current_idx = 0
        self.num_workers = len(workers)

        # Get default parameters from first worker (blocking)
        if RAY_AVAILABLE and workers:
            import ray
            # Note: We don't have direct access to worker attributes
            # So we'll track temperature/top_p separately
            self.temperature = 0.0
            self.top_p = 0.1
            self.max_tokens = 20000

        logger.info(f"RoundRobinLLMClient initialized with {self.num_workers} workers")

    def _get_next_worker(self):
        """Get next worker using round-robin"""
        worker = self.workers[self.current_idx]
        self.current_idx = (self.current_idx + 1) % self.num_workers
        return worker

    def chat(self, system: str, user: str,
            temperature: Optional[float] = None,
            top_p: Optional[float] = None,
            max_tokens: Optional[int] = None) -> str:
        """Send chat request to next available worker"""
        if not RAY_AVAILABLE:
            raise RuntimeError("Ray is not available")

        import ray
        worker = self._get_next_worker()
        result_ref = worker.chat.remote(
            system=system,
            user=user,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens
        )
        return ray.get(result_ref)

    def complete(self, prompt: str,
                temperature: Optional[float] = None,
                top_p: Optional[float] = None,
                max_tokens: Optional[int] = None) -> str:
        """Send completion request to next available worker"""
        if not RAY_AVAILABLE:
            raise RuntimeError("Ray is not available")

        import ray
        worker = self._get_next_worker()
        result_ref = worker.complete.remote(
            prompt=prompt,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens
        )
        return ray.get(result_ref)


def create_distributed_llm_client(
    num_gpus: int,
    endpoints_csv: str,
    model_name: str,
    temperature: float = 0.0,
    top_p: float = 0.1,
    max_tokens: int = 20000
) -> RoundRobinLLMClient:
    """
    Create distributed LLM client using Ray workers on multiple GPUs.

    Args:
        num_gpus: Number of GPUs to use
        endpoints_csv: Comma-separated vLLM endpoints
        model_name: Model name
        temperature: Default temperature
        top_p: Default top_p
        max_tokens: Default max_tokens

    Returns:
        RoundRobinLLMClient that distributes work across GPU workers
    """
    # Parse endpoints
    endpoints = [ep.strip() for ep in endpoints_csv.split(',') if ep.strip()]

    if not endpoints:
        raise ValueError("No vLLM endpoints provided")

    # Create workers
    workers = create_gpu_llm_workers(
        num_gpus=num_gpus,
        endpoints=endpoints,
        model_name=model_name,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens
    )

    # Wrap in round-robin client
    return RoundRobinLLMClient(workers)
