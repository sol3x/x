# utils/config_manager.py
from configparser import ConfigParser

class ConfigManager:
    """
    کلاسی برای خواندن و مدیریت تنظیمات از فایل config.ini.
    این کلاس به عنوان یک رابط واحد برای دسترسی به تمام پارامترهای پیکربندی
    در سراسر پروژه عمل می‌کند.
    """
    def __init__(self, filename='config.ini'):
        self.config = ConfigParser()
        if not self.config.read(filename, encoding='utf-8'):
            raise FileNotFoundError(f"فایل پیکربندی '{filename}' پیدا نشد. لطفاً آن را بسازید.")

    def get(self, section, key, fallback=None):
        """یک مقدار رشته‌ای را از فایل کانفیگ می‌خواند."""
        return self.config.get(section, key, fallback=fallback)

    def getint(self, section, key, fallback=0):
        """یک مقدار عددی صحیح (integer) را از فایل کانفیگ می‌خواند."""
        return self.config.getint(section, key, fallback=fallback)

    def getfloat(self, section, key, fallback=0.0):
        """یک مقدار عددی اعشاری (float) را از فایل کانفیگ می‌خواند."""
        return self.config.getfloat(section, key, fallback=fallback)
