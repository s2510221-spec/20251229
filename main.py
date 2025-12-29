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
st.markdown("데이터에 있는 **실제 장소명**을 기반으로 안전한 경로를 안내합니다.")

# ---------------------------------------------------------
# 2. 데이터 로드 및 오류 방지 전처리
# ---------------------------------------------------------
@st.cache_data
def load_data_safe():
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
        return pd.DataFrame()

    # 2) [핵심 수정] 인덱스 초기화 (ValueError: duplicate labels 해결)
    # 데이터가 섞이거나 병합될 때 인덱스가 꼬이는 것을 방지합니다.
    df = df.reset_index(drop=True)

    # 3) 컬럼 자동 매핑
    rename_map = {}
    for col in df.columns:
        c_low = col.lower()
        if any(x in c_low for x in ['lat', '위도', 'y좌표']): rename_map[col] = 'lat'
        elif any(x in c_low for x in ['lon', '경도', 'x좌표']): rename_map[col] = 'lon'
        elif any(x in c_low for x in ['name', '장소', '도로', '지점', '구간']): rename_map[col] = 'road_name'
        elif any(x in c_low for x in ['risk', '위험', 'score']): rename_map[col] = 'risk_score'
    
    df = df.rename(columns=rename_map)

    # 4) 좌표 데이터 검증
    if 'lat' not in df.columns or 'lon' not in df.columns:
        # 컬럼 이름으로 못 찾으면 값 범위로 찾기
        num_cols = df.select_dtypes(include=[np.number]).columns
        for c in num_cols:
            mean_val = df[c].mean()
            if 33 <= mean_val <= 39: df['lat'] = df[c]
            elif 124 <= mean_val <= 132: df['lon'] = df[c]

    if 'lat' in df.columns and 'lon' in df.columns:
        df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
        df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
        df = df.dropna(subset=['lat', 'lon'])
    else:
        st.error("데이터에서 좌표 정보를 찾을 수 없습니다.")
        return pd.DataFrame()

    # 5) [핵심 수정] 이름 데이터 정리
    if 'road_name' not in df.columns:
        # 이름 컬럼이 없으면 첫번째 문자열 컬럼을 사용
        obj_cols = df.select_dtypes(include=['object']).columns
        if len(obj_cols) > 0:
            df['road_name'] = df[obj_cols[0]]
        else:
            # 진짜 이름이 없을 때만 임시 이름 생성
            df['road_name'] = [f"지점_{i}" for i in range(len(df))]
    
    # 이름을 문자열로 변환하고 빈 값 채움
    df['road_name'] = df['road_name'].fillna("이름없음").astype(str)

    # 6) [핵심 수정] 이름 중복 제거
    # 똑같은 이름(예: '강남대로')이 10개 있으면 검색 시 에러가 납니다.
    # 이름 기준으로 중복을 제거하여 유일한 값만 남깁니다.
    df = df.drop_duplicates(subset=['road_name'])

    # 위험도 점수 (없으면 랜덤)
    if 'risk_score' not in df.columns:
        df['risk_score'] = np.random.randint(1, 100, len(df))

    return df

df = load_data_safe()

# 데이터 로드 실패 시 중단
if df is None or df.empty:
    st.stop()

# ---------------------------------------------------------
# 3. 사이드바 설정 (실제 이름 사용)
# ---------------------------------------------------------
st.sidebar.header("📍 경로 설정")

# 모드 선택
mode = st.sidebar.radio("이동 수단", ["🚗 자동차 (빠른길)", "🚶 보행자 (안전길)"])

# 장소 목록 (데이터에 있는 실제 이름 정렬)
place_list = sorted(df['road_name'].unique())

start_node = st.sidebar.selectbox("출발지 선택", place_list, index=0)
end_node = st.sidebar.selectbox("도착지 선택", place_list, index=1 if len(place_list) > 1 else 0)

run_btn = st.sidebar.button("경로 분석 시작")

# ---------------------------------------------------------
# 4. 지도 시각화
# ---------------------------------------------------------
# 초기 지도: 대한민국 전체
m = folium.Map(location=[36.5, 127.5], zoom_start=7)

if run_btn:
    if start_node == end_node:
        st.warning("출발지와 도착지가 같습니다.")
    else:
        # 1. 선택한 이름으로 좌표 찾기 (중복 제거했으므로 안전함)
        s_row = df[df['road_name'] == start_node].iloc[0]
        e_row = df[df['road_name'] == end_node].iloc[0]
        
        s_loc = [s_row['lat'], s_row['lon']]
        e_loc = [e_row['lat'], e_row['lon']]
        
        # 2. 지도 중심 이동
        mid_lat = (s_loc[0] + e_loc[0]) / 2
        mid_lon = (s_loc[1] + e_loc[1]) / 2
        m.location = [mid_lat, mid_lon]
        m.zoom_start = 12
        
        # 3. 출발/도착 마커
        folium.Marker(s_loc, popup=f"출발: {start_node}", icon=folium.Icon(color='blue', icon='play')).add_to(m)
        folium.Marker(e_loc, popup=f"도착: {end_node}", icon=folium.Icon(color='red', icon='flag')).add_to(m)
        
        # 4. 직선 거리 및 주변 탐색 범위 설정
        dist = math.sqrt((s_loc[0]-e_loc[0])**2 + (s_loc[1]-e_loc[1])**2) * 111
        
        # 화면에 보이는 범위 내의 데이터만 필터링
        bounds = [
            min(s_loc[0], e_loc[0])-0.03, max(s_loc[0], e_loc[0])+0.03,
            min(s_loc[1], e_loc[1])-0.03, max(s_loc[1], e_loc[1])+0.03
        ]
        
        # 좌표값 기준으로 필터링 (Pandas between 사용)
        nearby = df[
            (df['lat'].between(bounds[0], bounds[1])) & 
            (df['lon'].between(bounds[2], bounds[3]))
        ]
        
        # -----------------------------------------
        # 🚗 vs 🚶 모드별 차별화
        # -----------------------------------------
        if "자동차" in mode:
            # 자동차: 파란색 실선 + 클러스터링(정보 요약)
            folium.PolyLine([s_loc, e_loc], color='#2E86C1', weight=8, opacity=0.8, tooltip="추천 주행 경로").add_to(m)
            
            cluster = MarkerCluster().add_to(m)
            for _, r in nearby.iterrows():
                # 출발/도착지 제외
                if r['road_name'] in [start_node, end_node]: continue
                
                sc = r['risk_score']
                c = 'green' if sc < 30 else ('orange' if sc < 70 else 'red')
                
                folium.CircleMarker(
                    [r['lat'], r['lon']], radius=5, color=c, fill=True, fill_color=c,
                    popup=f"<b>{r['road_name']}</b><br>위험도: {int(sc)}"
                ).add_to(cluster)
            
            # 정보 패널
            est_time = (dist / 40) * 60
            st.info(f"🚘 **자동차 모드 결과 ({start_node} → {end_node})**")
            c1, c2, c3 = st.columns(3)
            c1.metric("이동 거리", f"{dist:.2f} km")
            c2.metric("예상 소요 시간", f"{int(est_time)} 분")
            c3.metric("경로 주변 정보", f"{len(nearby)} 건")
            
        else:
            # 보행자: 초록색 점선 + 위험 지역만 경고
            folium.PolyLine([s_loc, e_loc], color='#27AE60', weight=6, dash_array='10', tooltip="추천 보행 경로").add_to(m)
            
            risk_cnt = 0
            for _, r in nearby.iterrows():
                if r['road_name'] in [start_node, end_node]: continue
                
                # 70점 이상인 위험 지역만 표시
                if r['risk_score'] >= 70:
                    folium.Marker(
                        [r['lat'], r['lon']],
                        icon=folium.Icon(color='red', icon='exclamation-triangle', prefix='fa'),
                        tooltip=f"⚠️ 주의: {r['road_name']}"
                    ).add_to(m)
                    risk_cnt += 1
            
            # 정보 패널
            walk_time = (dist / 4) * 60
            kcal = dist * 50
            st.success(f"🚶 **보행자 모드 결과 ({start_node} → {end_node})**")
            c1, c2, c3 = st.columns(3)
            c1.metric("이동 거리", f"{dist:.2f} km")
            c2.metric("도보 소요 시간", f"{int(walk_time)} 분")
            c3.metric("소모 칼로리", f"{int(kcal)} kcal")
            
            if risk_cnt > 0:
                st.toast(f"경로상 주의해야 할 곳이 {risk_cnt}곳 있습니다.", icon="⚠️")

# 지도 출력
st_folium(m, width=None, height=550, use_container_width=True)
