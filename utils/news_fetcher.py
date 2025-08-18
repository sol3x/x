# utils/news_fetcher.py
# نسخه ۲.۰ - بازنویسی کامل برای استفاده از API مستقیم JSON به جای Web Scraping

import requests
from datetime import datetime, date
import pytz
import time

# --- متغیرهای سراسری برای کش کردن داده‌های اخبار ---
# این کار از ارسال درخواست‌های مکرر به وب‌سایت جلوگیری می‌کند.
news_cache = {
    "last_fetch_date": None,
    "events": []
}

# URL مستقیم API برای دریافت تقویم هفتگی
NEWS_API_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

def get_todays_high_impact_news(target_currencies, min_impact='High'):
    """
    اخبار اقتصادی را برای هفته جاری از API دریافت کرده و رویدادهای مهم امروز را فیلتر می‌کند.
    نتایج به صورت روزانه کش می‌شوند تا از ارسال درخواست‌های مکرر جلوگیری شود.
    """
    global news_cache
    today = date.today()

    # اگر داده‌های امروز قبلاً دریافت شده‌اند، از کش استفاده کن
    if news_cache["last_fetch_date"] == today:
        return news_cache["events"]

    print("Fetching weekly economic news from API...")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(NEWS_API_URL, headers=headers, timeout=15)
        response.raise_for_status()
        all_events_this_week = response.json()

        todays_events = []
        # نقشه برای تبدیل سطح اهمیت متنی به عددی برای مقایسه آسان‌تر
        impact_map = {'High': 3, 'Medium': 2, 'Low': 1}
        min_impact_level = impact_map.get(min_impact, 3) # پیش‌فرض High است

        for event in all_events_this_week:
            # تبدیل رشته تاریخ از فرمت ISO به شیء datetime با منطقه زمانی UTC
            event_dt_utc = datetime.fromisoformat(event['date'].replace('Z', '+00:00'))
            
            # فیلتر کردن رویدادها برای روز جاری
            if event_dt_utc.date() == today:
                event_impact_level = impact_map.get(event['impact'], 0)
                
                # فیلتر کردن بر اساس ارز و سطح اهمیت
                if event['country'] in target_currencies and event_impact_level >= min_impact_level:
                    todays_events.append(event_dt_utc)
        
        # به‌روزرسانی کش
        news_cache["last_fetch_date"] = today
        news_cache["events"] = todays_events
        
        print(f"Found {len(todays_events)} relevant news events for today.")
        return todays_events

    except requests.exceptions.RequestException as e:
        print(f"Error fetching news data from API: {e}")
        return [] # در صورت خطا، لیست خالی برگردان تا ربات متوقف نشود
    except Exception as e:
        print(f"An unexpected error occurred while parsing news JSON: {e}")
        return []
