import threading
import time
from typing import Dict, List, Optional

from .log_config import logger


class SimpleMemoryCache:
    """
    Simplified memory-safe cache with basic eviction.
    Optimized for performance without detailed monitoring.
    """
    
    def __init__(self, max_memory_mb: int = 50, max_items: int = 500, ttl_seconds: int = 300):
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self.max_items = max_items
        self.ttl_seconds = ttl_seconds
        
        self._cache = {}
        self._access_times = {}
        self._memory_usage = 0
        self._lock = threading.RLock()
        self._last_cleanup = time.time()
        
        logger.info(f"Initialized simple cache: {max_memory_mb}MB limit, {max_items} items max")
    
    def _get_content_size(self, content: str) -> int:
        """Get approximate memory size of content in bytes."""
        return len(content.encode('utf-8'))
    
    def _evict_items(self):
        """Evict oldest items to free memory."""
        target_memory = int(self.max_memory_bytes * 0.8)
        
        # Sort by access time (oldest first)
        items_by_access = sorted(self._access_times.items(), key=lambda x: x[1])
        
        for key, _ in items_by_access:
            if self._memory_usage <= target_memory and len(self._cache) <= self.max_items:
                break
                
            if key in self._cache:
                content_size = self._get_content_size(self._cache[key])
                self._cache.pop(key, None)
                self._access_times.pop(key, None)
                self._memory_usage -= content_size
    
    def get(self, key: str) -> Optional[str]:
        """Get cached value."""
        current_time = time.time()
        
        with self._lock:
            if key in self._cache:
                access_time = self._access_times.get(key, 0)
                if current_time - access_time < self.ttl_seconds:
                    self._access_times[key] = current_time
                    return self._cache[key]
                else:
                    # Expired, remove
                    content_size = self._get_content_size(self._cache[key])
                    self._cache.pop(key, None)
                    self._access_times.pop(key, None)
                    self._memory_usage -= content_size
            
            # Periodic cleanup
            if current_time - self._last_cleanup > 300:
                self._cleanup_expired(current_time)
                self._last_cleanup = current_time
                
        return None
    
    def set(self, key: str, value: str):
        """Set cache value."""
        content_size = self._get_content_size(value)
        
        # Skip very large documents
        if content_size > 1024 * 1024:
            return
        
        current_time = time.time()
        
        with self._lock:
            # Check memory limits
            new_memory_usage = self._memory_usage + content_size
            if key in self._cache:
                new_memory_usage -= self._get_content_size(self._cache[key])
            
            # Evict if necessary
            if (new_memory_usage > self.max_memory_bytes or 
                len(self._cache) >= self.max_items):
                self._evict_items()
            
            # Update cache
            if key in self._cache:
                old_size = self._get_content_size(self._cache[key])
                self._memory_usage -= old_size
            
            self._cache[key] = value
            self._access_times[key] = current_time
            self._memory_usage += content_size
    
    def get_many(self, keys: List[str]) -> Dict[str, str]:
        """Get multiple cached values."""
        result = {}
        current_time = time.time()
        
        with self._lock:
            for key in keys:
                if key in self._cache:
                    access_time = self._access_times.get(key, 0)
                    if current_time - access_time < self.ttl_seconds:
                        result[key] = self._cache[key]
                        self._access_times[key] = current_time
                    else:
                        # Expired, remove
                        content_size = self._get_content_size(self._cache[key])
                        self._cache.pop(key, None)
                        self._access_times.pop(key, None)
                        self._memory_usage -= content_size
        
        return result
    
    def set_many(self, items: Dict[str, str]):
        """Set multiple cache values."""
        current_time = time.time()
        
        with self._lock:
            for key, value in items.items():
                content_size = self._get_content_size(value)
                
                # Skip large documents
                if content_size > 1024 * 1024:
                    continue
                
                # Check memory limits
                new_memory_usage = self._memory_usage + content_size
                if key in self._cache:
                    new_memory_usage -= self._get_content_size(self._cache[key])
                
                if (new_memory_usage > self.max_memory_bytes or 
                    len(self._cache) >= self.max_items):
                    self._evict_items()
                
                # Update cache
                if key in self._cache:
                    old_size = self._get_content_size(self._cache[key])
                    self._memory_usage -= old_size
                
                self._cache[key] = value
                self._access_times[key] = current_time
                self._memory_usage += content_size
    
    def _cleanup_expired(self, current_time: float):
        """Remove expired entries."""
        expired_keys = [
            key for key, access_time in self._access_times.items()
            if current_time - access_time >= self.ttl_seconds
        ]
        
        for key in expired_keys:
            if key in self._cache:
                self._memory_usage -= self._get_content_size(self._cache[key])
                self._cache.pop(key, None)
            self._access_times.pop(key, None)
    
    def clear(self):
        """Clear all cached data."""
        with self._lock:
            self._cache.clear()
            self._access_times.clear()
            self._memory_usage = 0
        logger.info("Cache cleared")
