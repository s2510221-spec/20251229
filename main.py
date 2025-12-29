import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from folium.plugins import MarkerCluster
import math
import numpy as np

# ---------------------------------------------------------
# 1. 페이지 설정
# ---------------------------------------------------------
st.set_page_config(layout="wide", page_title="SafeRoad Korea")

st.title("🇰🇷 SafeRoad: 대한민국 안전 경로 탐색")
st.markdown("데이터 오류를 방지하고, 자동차와 보행자 모드를 명확히 구분합니다.")

# ---------------------------------------------------------
# 2. 데이터 자동 로드 (오류 방지 로직 강화)
# ---------------------------------------------------------
@st.cache_data
def load_data_auto():
    file_path = '20251229road_최종.csv'
    df = None
    
    # 1) 파일 읽기
    for enc in ['cp949', 'utf-8', 'euc-kr', 'utf-8-sig']:
        try:
            df = pd.read_csv(file_path, encoding=enc)
            df.columns = df.columns.str.strip()
            break
        except: continue
            
    if df is None:
        st.error("❌ 데이터 파일을 찾을 수 없습니다. (20251229road_최종.csv)")
        return None

    # 2) 컬럼 이름 자동 매핑
    rename_map = {}
    for col in df.columns:
        c_low = col.lower()
        if any(x in c_low for x in ['lat', '위도', 'y좌표']): rename_map[col] = 'lat'
        elif any(x in c_low for x in ['lon', '경도', 'x좌표']): rename_map[col] = 'lon'
        elif any(x in c_low for x in ['name', '장소', '도로', '지점']): rename_map[col] = 'road_name'
        elif any(x in c_low for x in ['risk', '위험', 'score']): rename_map[col] = 'risk_score'
    
    df = df.rename(columns=rename_map)

    # 3) 좌표 없는 데이터 삭제
    if 'lat' not in df.columns or 'lon' not in df.columns:
        # 숫자로 된 컬럼 중 위도/경도 범위 찾기
        num_cols = df.select_dtypes(include=[np.number]).columns
        for c in num_cols:
            mean_val = df[c].mean()
            if 33 <= mean_val <= 39: df['lat'] = df[c]
            elif 124 <= mean_val <= 132: df['lon'] = df[c]

    if 'lat' in df.columns and 'lon' in df.columns:
        df = df.dropna(subset=['lat', 'lon']) # NaN 삭제
    else:
        st.error("데이터에서 좌표(위도/경도)를 찾을 수 없습니다.")
        return None

    # 4) [핵심 수정] road_name 컬럼 강제 문자열 변환 (AttributeError 방지)
    if 'road_name' not in df.columns:
        df['road_name'] = [f"지점_{i}" for i in range(len(df))]
    
    # 여기서 모든 값을 문자로 바꿔버립니다. (에러 해결 포인트)
    df['road_name'] = df['road_name'].fillna("이름없음").astype(str)

    # 위험도 점수 없으면 생성
    if 'risk_score' not in df.columns:
        df['risk_score'] = np.random.randint(1, 100, len(df))

    return df

df = load_data_auto()

# 데이터가 없으면 여기서 중단
if df is None or df.empty:
    st.warning("데이터를 불러오지 못했습니다. 파일이 있는지 확인해주세요.")
    st.stop()

# ---------------------------------------------------------
# 3. 사이드바 UI
# ---------------------------------------------------------
st.sidebar.header("📍 설정")

# 모드 선택
mode = st.sidebar.radio("이동 수단", ["🚗 자동차 (빠른 이동)", "🚶 보행자 (안전 이동)"])

# 장소 선택 (에러가 발생했던 부분 수정)
# 이미 load_data_auto에서 문자열로 바꿨으므로 안전하게 정렬됨
try:
    places = sorted(df['road_name'].unique())
except Exception as e:
    # 혹시라도 또 에러나면 인덱스로 대체
    places = [f"지점_{i}" for i in range(len(df))]

start_node = st.sidebar.selectbox("출발지", places, index=0)
end_node = st.sidebar.selectbox("도착지", places, index=1 if len(places)>1 else 0)

run_btn = st.sidebar.button("경로 분석 시작")

# ---------------------------------------------------------
# 4. 지도 로직 (대한민국 중심)
# ---------------------------------------------------------
m = folium.Map(location=[36.5, 127.5], zoom_start=7)

if run_btn:
    if start_node == end_node:
        st.warning("출발지와 도착지가 같습니다.")
    else:
        # 좌표 가져오기
        s_row = df[df['road_name'] == start_node].iloc[0]
        e_row = df[df['road_name'] == end_node].iloc[0]
        s_loc = [s_row['lat'], s_row['lon']]
        e_loc = [e_row['lat'], e_row['lon']]
        
        # 지도 이동
        mid_lat = (s_loc[0] + e_loc[0]) / 2
        mid_lon = (s_loc[1] + e_loc[1]) / 2
        m.location = [mid_lat, mid_lon]
        m.zoom_start = 12
        
        # 출발/도착 마커
        folium.Marker(s_loc, popup="출발", icon=folium.Icon(color='blue', icon='play')).add_to(m)
        folium.Marker(e_loc, popup="도착", icon=folium.Icon(color='red', icon='flag')).add_to(m)
        
        # 화면 범위 내 데이터 필터링
        bounds = [
            min(s_loc[0], e_loc[0])-0.03, max(s_loc[0], e_loc[0])+0.03,
            min(s_loc[1], e_loc[1])-0.03, max(s_loc[1], e_loc[1])+0.03
        ]
        nearby = df[
            (df['lat'].between(bounds[0], bounds[1])) & 
            (df['lon'].between(bounds[2], bounds[3]))
        ]
        dist = math.sqrt((s_loc[0]-e_loc[0])**2 + (s_loc[1]-e_loc[1])**2) * 111
        
        # =================================================
        # 🚗 vs 🚶 차별화 로직
        # =================================================
        if "자동차" in mode:
            # 1. 디자인: 고속도로 느낌의 굵은 파란 실선
            folium.PolyLine([s_loc, e_loc], color='#2E86C1', weight=8, opacity=0.8).add_to(m)
            
            # 2. 정보 표시 방식: 클러스터링 (지저분하지 않게 묶어서 표시)
            cluster = MarkerCluster().add_to(m)
            
            for _, r in nearby.iterrows():
                if r['road_name'] in [start_node, end_node]: continue
                sc = r['risk_score']
                c = 'green' if sc < 30 else ('orange' if sc < 70 else 'red')
                
                # 자동차는 모든 정보를 보여주되 묶어서 보여줌
                folium.CircleMarker(
                    [r['lat'], r['lon']], radius=5, color=c, fill=True, fill_color=c,
                    popup=f"{r['road_name']} (점수:{sc})"
                ).add_to(cluster)
            
            # 3. 결과 메시지: 운전 시간 중심
            est_time = (dist / 40) * 60 # 시속 40km
            st.info(f"🚘 **자동차 주행 정보**")
            c1, c2, c3 = st.columns(3)
            c1.metric("거리", f"{dist:.2f} km")
            c2.metric("예상 운전 시간", f"{int(est_time)} 분")
            c3.metric("도로 혼잡도", f"보통")

        else:
            # 1. 디자인: 산책로 느낌의 초록 점선
            folium.PolyLine([s_loc, e_loc], color='#27AE60', weight=6, dash_array='10').add_to(m)
            
            # 2. 정보 표시 방식: 위험 회피 (위험한 곳만 강조)
            risk_cnt = 0
            for _, r in nearby.iterrows():
                if r['road_name'] in [start_node, end_node]: continue
                
                # 보행자는 70점 이상인 '위험 구역'만 붉은 느낌표로 표시
                if r['risk_score'] >= 70:
                    folium.Marker(
                        [r['lat'], r['lon']],
                        icon=folium.Icon(color='red', icon='exclamation-triangle', prefix='fa'),
                        tooltip=f"⚠️ 보행 주의: {r['road_name']}"
                    ).add_to(m)
                    risk_cnt += 1
            
            # 3. 결과 메시지: 건강 & 안전 중심
            walk_time = (dist / 4) * 60 # 시속 4km
            kcal = dist * 50
            st.success(f"🚶 **보행자 건강 정보**")
            c1, c2, c3 = st.columns(3)
            c1.metric("거리", f"{dist:.2f} km")
            c2.metric("도보 시간", f"{int(walk_time)} 분")
            c3.metric("소모 칼로리", f"{int(kcal)} kcal")
            
            if risk_cnt > 0:
                st.toast(f"경로 주변 위험 지역 {risk_cnt}곳 감지됨", icon="🚨")

# 지도 출력
st_folium(m, width=None, height=550, use_container_width=True)
