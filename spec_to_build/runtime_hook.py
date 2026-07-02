# runtime_hook.py - сохраните в папке проекта
import sys
import os

# Создаем фейковую метаданные для imageio
class FakeDistribution:
    def __init__(self, name, version):
        self._name = name
        self._version = version
    
    @property
    def version(self):
        return self._version

# Подменяем importlib.metadata
try:
    import importlib.metadata as metadata
    
    # Сохраняем оригинальную функцию
    original_distribution = metadata.distribution
    
    def patched_distribution(package_name):
        if package_name == 'imageio':
            return FakeDistribution('imageio', '2.37.3')
        return original_distribution(package_name)
    
    metadata.distribution = patched_distribution
    
    # Также патчим version
    original_version = metadata.version
    def patched_version(package_name):
        if package_name == 'imageio':
            return '2.37.3'
        return original_version(package_name)
    
    metadata.version = patched_version
    
    print("[Runtime Hook] ImageIO metadata patch applied")
except Exception as e:
    print(f"[Runtime Hook] Error: {e}")

# Добавляем imageio в sys.modules если его нет
try:
    import imageio
    print(f"[Runtime Hook] ImageIO loaded from: {imageio.__file__}")
except ImportError:
    print("[Runtime Hook] ImageIO not found, creating dummy")
    # Создаем dummy модуль если нужно
    import types
    dummy_imageio = types.ModuleType('imageio')
    dummy_imageio.__version__ = '2.37.3'
    sys.modules['imageio'] = dummy_imageio