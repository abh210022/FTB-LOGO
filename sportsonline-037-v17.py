from datetime import datetime, timedelta
from io import BytesIO
import json
import os
import re
from bs4 import BeautifulSoup
from PIL import Image
import requests

# ================= CONFIGURATION =================
PROG_URL = "https://sportsonline.st/prog.txt"
SAVE_DIR = r"D:\sportsonline"
IMAGE_SAVE_DIR = os.path.join(SAVE_DIR, "images")
SAVE_FILE = os.path.join(SAVE_DIR, "sportsonline.w3u")

# ตั้งค่า GitHub และ jsDelivr CDN ตามที่คุณระบุ
GITHUB_USER = "abh210022"
REPO_NAME = "FTB-LOGO"
BRANCH = "main"

HEADER_IMAGE = "https://drive.google.com/uc?id=1F1Rw4jTwr6YPU-esWsTT2HkFP-JdngAA&export=download"
GROUP_IMAGE = "https://drive.google.com/uc?id=1VVIg15m3Y3J8VtFGtNq10MToP7Zg0NVi&export=download"
DEFAULT_MATCH_IMAGE = "https://drive.google.com/uc?id=1VVIg15m3Y3J8VtFGtNq10MToP7Zg0NVi&export=download"

match_database = {}

OTHER_SPORTS_KEYWORDS = {
    "Tennis": "Tennis",
    "ATP": "Tennis",
    "WTA": "Tennis",
    "NBA": "Basketball",
    "Basketball": "Basketball",
    "Formula 1": "F1",
    "F1": "F1",
    "MotoGP": "MotoGP",
    "UFC": "UFC",
    "Boxing": "Boxing",
    "NFL": "NFL",
    "Snooker": "Snooker",
    "Badminton": "Badminton",
    "Volleyball": "Volleyball",
}

DAY_NAME_MAP = {
    "MONDAY": 0,
    "TUESDAY": 1,
    "WEDNESDAY": 2,
    "THURSDAY": 3,
    "FRIDAY": 4,
    "SATURDAY": 5,
    "SUNDAY": 6,
}

# ================= HELPER FUNCTIONS =================


def get_base_date_from_dayname(day_name_str):
  today = datetime.utcnow() + timedelta(hours=7)
  today = today.replace(hour=0, minute=0, second=0, microsecond=0)
  today_idx = today.weekday()
  target_idx = DAY_NAME_MAP.get(day_name_str.upper())
  if target_idx is None:
    return None
  diff = target_idx - today_idx
  if diff < -1:
    diff += 7
  return today + timedelta(days=diff)


def extract_channel_name(url):
  try:
    filename = url.split("/")[-1]
    channel = filename.split(".")[0]
    return channel
  except:
    return ""


# 1. ฟังก์ชันสร้างภาพกราฟิกคู่แข่งขันและคืนค่าเป็น jsDelivr CDN URL
def generate_fixture_image(league_url, home_url, away_url, match_id):
  os.makedirs(IMAGE_SAVE_DIR, exist_ok=True)
  filename = f"fixture_{match_id}.png"
  file_path = os.path.join(IMAGE_SAVE_DIR, filename)

  # สร้าง URL สำเร็จรูปสำหรับ jsDelivr CDN
  cdn_url = f"https://cdn.jsdelivr.net/gh/{GITHUB_USER}/{REPO_NAME}@{BRANCH}/images/{filename}"

  # หากมีไฟล์อยู่แล้ว ข้ามการเรนเดอร์ซ้ำเพื่อความรวดเร็ว
  if os.path.exists(file_path):
    return cdn_url

  try:
    league_res = requests.get(
        league_url if league_url else DEFAULT_MATCH_IMAGE, timeout=10
    )
    home_res = requests.get(
        home_url if home_url else DEFAULT_MATCH_IMAGE, timeout=10
    )
    away_res = requests.get(
        away_url if away_url else DEFAULT_MATCH_IMAGE, timeout=10
    )

    league_img = Image.open(BytesIO(league_res.content)).convert("RGBA")
    home_img = Image.open(BytesIO(home_res.content)).convert("RGBA")
    away_img = Image.open(BytesIO(away_res.content)).convert("RGBA")
  except Exception:
    return DEFAULT_MATCH_IMAGE

  # สัดส่วนขนาด (โลโก้ลีกตรงกลางเล็กกว่า, ทีมเหย้า-เยือนใหญ่เด่นชัด)
  team_size = (130, 130)
  league_size = (75, 75)

  home_img = home_img.resize(team_size, Image.Resampling.LANCZOS)
  away_img = away_img.resize(team_size, Image.Resampling.LANCZOS)
  league_img = league_img.resize(league_size, Image.Resampling.LANCZOS)

  padding = 15
  spacing = 20

  total_width = (
      (padding * 2)
      + team_size[0]
      + spacing
      + league_size[0]
      + spacing
      + team_size[0]
  )
  max_height = max(team_size[1], league_size[1])
  total_height = (padding * 2) + max_height

  # แคนวาสพื้นหลังโปร่งใส (Transparent PNG)
  canvas = Image.new("RGBA", (total_width, total_height), (0, 0, 0, 0))

  home_y = padding + (max_height - team_size[1]) // 2
  league_y = padding + (max_height - league_size[1]) // 2
  away_y = padding + (max_height - team_size[1]) // 2

  home_x = padding
  league_x = home_x + team_size[0] + spacing
  away_x = league_x + league_size[0] + spacing

  canvas.paste(home_img, (home_x, home_y), home_img)
  canvas.paste(league_img, (league_x, league_y), league_img)
  canvas.paste(away_img, (away_x, away_y), away_img)

  canvas.save(file_path, "PNG")
  return cdn_url


# ================= MAIN PIPELINE =================


def process_and_fetch_dates(lines):
  dates_to_scrape = set()
  processed_matches = []
  current_gmt1_base_date = None
  last_gmt1_time_obj = None
  gmt1_days_offset = 0

  for line in lines:
    line = line.strip()
    if not line:
      continue
    if line.upper() in DAY_NAME_MAP:
      current_gmt1_base_date = get_base_date_from_dayname(line.upper())
      last_gmt1_time_obj = None
      gmt1_days_offset = 0
      continue

    m = re.match(r"(\d{2}:\d{2})\s+(.*?)\s+\|\s+(https?://\S+)", line)
    if m and current_gmt1_base_date:
      time_str, title, url = m.groups()
      current_time = datetime.strptime(time_str, "%H:%M")
      if last_gmt1_time_obj is not None and current_time < last_gmt1_time_obj:
        gmt1_days_offset += 1
      last_gmt1_time_obj = current_time

      match_date_gmt1 = current_gmt1_base_date + timedelta(
          days=gmt1_days_offset
      )
      full_dt_gmt1 = datetime.combine(
          match_date_gmt1.date(), current_time.time()
      )
      full_dt_thai = full_dt_gmt1 + timedelta(hours=6)

      thai_date_str = full_dt_thai.strftime("%Y-%m-%d")
      dates_to_scrape.add(thai_date_str)

      processed_matches.append({
          "thai_datetime": full_dt_thai,
          "time_show": full_dt_thai.strftime("%H:%M"),
          "title": title,
          "url": url,
          "channel": extract_channel_name(url),
          "date_str": thai_date_str,
      })

  return sorted(list(dates_to_scrape)), processed_matches


def fetch_037score_for_dates(dates_set):
  headers = {"User-Agent": "Mozilla/5.0"}
  for date_str in dates_set:
    url = f"https://037score.com/en?date={date_str}"
    print(f"กำลังดึงข้อมูลโลโก้จาก 037score สำหรับวันที่: {date_str}...")
    try:
      res = requests.get(url, headers=headers, timeout=20)
      if res.status_code != 200:
        continue
      soup = BeautifulSoup(res.text, "html.parser")

      for match in soup.select("a[href^='/en/match/']"):
        league_name, league_logo = "", ""
        league_img = match.select_one("img[alt][src*='/football/leagues/']")
        if league_img:
          league_logo = league_img["src"]
          league_name = league_img.get("alt", "").strip()
        if not league_name:
          league_span = match.select_one(
              "span.truncate.text-2xs.text-muted-foreground"
          )
          if league_span:
            league_name = league_span.get_text(strip=True)

        team_imgs = match.select("img[src*='/football/teams/']")
        if len(team_imgs) < 2:
          continue

        home_logo = team_imgs[0]["src"]
        away_logo = team_imgs[1]["src"]
        home_name = team_imgs[0].get("alt", "").strip().lower()
        away_name = team_imgs[1].get("alt", "").strip().lower()

        match_data = {
            "league_name": league_name or "Football",
            "league_logo": league_logo,
            "home_logo": home_logo,
            "away_logo": away_logo,
        }

        if home_name:
          match_database[home_name] = match_data
        if away_name:
          match_database[away_name] = match_data
    except Exception as e:
      print(f"⚠️ เกิดข้อผิดพลาดวันที่ {date_str}: {e}")


def get_match_logos_and_league(title):
  clean = title.replace(" x ", " vs ").replace("|", "")
  clean = re.sub(r"\d{2}:\d{2}", "", clean).strip()

  for k, v in OTHER_SPORTS_KEYWORDS.items():
    if k.lower() in clean.lower():
      return v, "", DEFAULT_MATCH_IMAGE, DEFAULT_MATCH_IMAGE

  teams = clean.split(" vs ") if " vs " in clean else [clean]
  league_name, league_logo, home_logo, away_logo = "Football", "", "", ""

  if len(teams) >= 2:
    h_key = teams[0].strip().lower()
    a_key = teams[1].strip().lower()

    if h_key in match_database:
      league_name = match_database[h_key]["league_name"]
      league_logo = match_database[h_key]["league_logo"]
      home_logo = match_database[h_key]["home_logo"]

    if a_key in match_database:
      if not league_logo:
        league_name = match_database[a_key]["league_name"]
        league_logo = match_database[a_key]["league_logo"]
      away_logo = match_database[a_key]["away_logo"]

    if not home_logo or not away_logo:
      for db_team, info in match_database.items():
        if not home_logo and (h_key in db_team or db_team in h_key):
          league_name = info["league_name"]
          league_logo = info["league_logo"]
          home_logo = info["home_logo"]
        if not away_logo and (a_key in db_team or db_team in a_key):
          if not league_logo:
            league_name = info["league_name"]
            league_logo = info["league_logo"]
          away_logo = info["away_logo"]

  return (
      league_name,
      league_logo,
      home_logo or DEFAULT_MATCH_IMAGE,
      away_logo or DEFAULT_MATCH_IMAGE,
  )


def generate_json_final(processed_matches):
  groups_map = {}

  for item in processed_matches:
    thai_date_obj = item["thai_datetime"].date()
    date_key = thai_date_obj.strftime("%Y-%m-%d")

    if date_key not in groups_map:
      yy = str(thai_date_obj.year + 543)[-2:]
      group_name = f"วันที่ {thai_date_obj.day}/{thai_date_obj.month}/{yy}"
      groups_map[date_key] = {
          "name": group_name,
          "image": GROUP_IMAGE,
          "stations": [],
      }

    league_name, league_logo, home_logo, away_logo = get_match_logos_and_league(
        item["title"]
    )
    match_id = (
        f"{date_key}_{re.sub(r'[^a-zA-Z0-9]', '_', item['title'])[:30]}"
    )
    fixture_image_url = generate_fixture_image(
        league_logo, home_logo, away_logo, match_id
    )

    channel_name = item["channel"]
    info_text = (
        f"{league_name}-{channel_name}" if league_name else channel_name
    )
    display = f"{item['time_show']} {item['title']}"

    groups_map[date_key]["stations"].append({
        "name": display,
        "image": fixture_image_url,  # ลิงก์ jsDelivr CDN ที่พร้อมนำไปใช้งาน
        "url": item["url"],
        "referer": "https://sportsonline.st",
        "info": info_text,
        "userAgent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0)"
            " Gecko/20100101 Firefox/147.0"
        ),
    })

  final_groups = [groups_map[k] for k in sorted(groups_map.keys())]
  now_th = datetime.utcnow() + timedelta(hours=7)
  today_str = now_th.strftime("%d/%m/%Y")

  output = {
      "name": f"update @{today_str}",
      "author": f"Update@{today_str}",
      "info": f"sportsonline.cv Update@{today_str}",
      "image": HEADER_IMAGE,
      "groups": final_groups,
  }

  os.makedirs(SAVE_DIR, exist_ok=True)
  with open(SAVE_FILE, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
  try:
    print("[STEP 1] กำลังอ่านข้อมูลโปรแกรมแข่งขันจาก sportsonline.st...")
    r = requests.get(PROG_URL, timeout=15)
    dates, matches = process_and_fetch_dates(r.text.splitlines())

    print(
        f"[STEP 2] พบวันที่ต้องดึงข้อมูลทั้งหมด {len(dates)} วัน กำลังดึงจาก"
        " 037score..."
    )
    fetch_037score_for_dates(dates)

    print("[STEP 3] กำลังสร้างภาพคู่แข่งขันและประมวลผลไฟล์ JSON...")
    generate_json_final(matches)

    full_path = os.path.abspath(SAVE_FILE)
    print(f"\n--- SUCCESS: กระบวนการทั้งหมดเสร็จสมบูรณ์ ---")
    print(f"บันทึกไฟล์ JSON ที่: {full_path}")
    print(f"บันทึกไฟล์ภาพทั้งหมดที่โฟลเดอร์: {IMAGE_SAVE_DIR}")
  except Exception as e:
    print(f"[ERROR]: {e}")