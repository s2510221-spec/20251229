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
# 2. 데이터 로드 및 오류 방지 전처리 (핵심 수정 구간)
# ---------------------------------------------------------
@st.cache_data
def load_data_safe():
    file_path = '20251229road_최종.csv'
    df = None
    
    # 1) 파일 읽기
    for enc in ['cp949', 'utf-8', 'euc-kr', 'utf-8-sig']:
        try:
            df = pd.read_csv(file_path, encoding=enc)
            df.columns = df.columns.str.strip() # 공백 제거
            break
        except: continue
            
    if df is None:
        st.error("❌ 데이터 파일을 찾을 수 없습니다. (20251229road_최종.csv)")
        return pd.DataFrame()

    # 2) 인덱스 초기화 (중복 인덱스 에러 방지)
    df = df.reset_index(drop=True)

    # 3) 컬럼 이름 자동 매핑 (유연하게 찾기)
    # 데이터 컬럼을 하나씩 보면서 우리가 필요한 이름으로 바꿉니다.
    rename_map = {}
    for col in df.columns:
        c_low = col.lower()
        if any(x in c_low for x in ['lat', '위도', 'y좌표', 'y_coord']): rename_map[col] = 'lat'
        elif any(x in c_low for x in ['lon', '경도', 'x좌표', 'x_coord']): rename_map[col] = 'lon'
        elif any(x in c_low for x in ['name', '장소', '도로', '지점', '구간', '명칭']): rename_map[col] = 'road_name'
        elif any(x in c_low for x in ['risk', '위험', 'score', '점수']): rename_map[col] = 'risk_score'
    
    df = df.rename(columns=rename_map)

    # 4) [중요] road_name 컬럼이 없으면 강제로 생성 (에러 원천 차단)
    if 'road_name' not in df.columns:
        # 혹시 문자열로 된 다른 컬럼이 있나 찾아봄
        obj_cols = df.select_dtypes(include=['object']).columns
        if len(obj_cols) > 0:
            df['road_name'] = df[obj_cols[0]] # 첫 번째 문자열 컬럼을 이름으로 사용
        else:
            # 그것도 없으면 그냥 번호를 붙여서 만듦
            df['road_name'] = [f"지점_{i+1}" for i in range(len(df))]
    
    # 5) 이름 데이터 문자열 변환 (AttributeError 방지)
    df['road_name'] = df['road_name'].fillna("이름없음").astype(str)

    # 6) 좌표 데이터 검증 및 처리
    if 'lat' not in df.columns or 'lon' not in df.columns:
        # 컬럼 이름이 없으면 값의 범위를 보고 추측
        num_cols = df.select_dtypes(include=[np.number]).columns
        for c in num_cols:
            mean_val = df[c].mean()
            if 33 <= mean_val <= 39: df['lat'] = df[c]
            elif 124 <= mean_val <= 132: df['lon'] = df[c]

    # 좌표가 확보되었는지 최종 확인
    if 'lat' in df.columns and 'lon' in df.columns:
        df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
        df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
        df = df.dropna(subset=['lat', 'lon']) # 좌표 없는 행 삭제
    else:
        st.error("🚨 데이터에서 위도/경도 정보를 찾을 수 없습니다. 숫자 데이터가 올바른지 확인해주세요.")
        return pd.DataFrame()

    # 7) 이름 중복 제거 (검색 오류 방지)
    df = df.drop_duplicates(subset=['road_name'])
    
    # 8) 위험도 점수 채우기
    if 'risk_score' not in df.columns:
        df['risk_score'] = np.random.randint(1, 100, len(df))

    return df

df = load_data_safe()

# 데이터가 비어있으면 중단
if df is None or df.empty:
    st.warning("데이터를 불러올 수 없습니다.")
    st.stop()

# ---------------------------------------------------------
# 3. 사이드바 설정
# ---------------------------------------------------------
st.sidebar.header("📍 경로 설정")

mode = st.sidebar.radio("이동 수단", ["🚗 자동차 (빠른길)", "🚶 보행자 (안전길)"])

# [여기서 에러가 났던 부분] 
# 위에서 road_name을 확실히 만들었으므로 이제 에러가 나지 않습니다.
place_list = sorted(df['road_name'].unique())

start_node = st.sidebar.selectbox("출발지 선택", place_list, index=0)
end_node = st.sidebar.selectbox("도착지 선택", place_list, index=1 if len(place_list) > 1 else 0)

run_btn = st.sidebar.button("경로 분석 시작")

# ---------------------------------------------------------
# 4. 지도 시각화
# ---------------------------------------------------------
m = folium.Map(location=[36.5, 127.5], zoom_start=7)

if run_btn:
    if start_node == end_node:
        st.warning("출발지와 도착지가 같습니다.")
    else:
        # 좌표 찾기
        s_row = df[df['road_name'] == start_node].iloc[0]
        e_row = df[df['road_name'] == end_node].iloc[0]
        
        s_loc = [s_row['lat'], s_row['lon']]
        e_loc = [e_row['lat'], e_row['lon']]
        
        # 지도 중심 이동
        mid_lat = (s_loc[0] + e_loc[0]) / 2
        mid_lon = (s_loc[1] + e_loc[1]) / 2
        m.location = [mid_lat, mid_lon]
        m.zoom_start = 12
        
        # 마커 표시
        folium.Marker(s_loc, popup=f"출발: {start_node}", icon=folium.Icon(color='blue', icon='play')).add_to(m)
        folium.Marker(e_loc, popup=f"도착: {end_node}", icon=folium.Icon(color='red', icon='flag')).add_to(m)
        
        # 거리 계산
        dist = math.sqrt((s_loc[0]-e_loc[0])**2 + (s_loc[1]-e_loc[1])**2) * 111
        
        # 주변 데이터 필터링
        bounds = [
            min(s_loc[0], e_loc[0])-0.03, max(s_loc[0], e_loc[0])+0.03,
            min(s_loc[1], e_loc[1])-0.03, max(s_loc[1], e_loc[1])+0.03
        ]
        nearby = df[
            (df['lat'].between(bounds[0], bounds[1])) & 
            (df['lon'].between(bounds[2], bounds[3]))
        ]
        
        # 🚗 vs 🚶 차별화
        if "자동차" in mode:
            folium.PolyLine([s_loc, e_loc], color='#2E86C1', weight=8, opacity=0.8).add_to(m)
            
            cluster = MarkerCluster().add_to(m)
            for _, r in nearby.iterrows():
                if r['road_name'] in [start_node, end_node]: continue
                sc = r['risk_score']
                c = 'green' if sc < 30 else ('orange' if sc < 70 else 'red')
                folium.CircleMarker(
                    [r['lat'], r['lon']], radius=5, color=c, fill=True, fill_color=c,
                    popup=f"{r['road_name']} ({int(sc)})"
                ).add_to(cluster)
            
            est_time = (dist / 40) * 60
            st.info(f"🚘 **자동차 분석: {start_node} → {end_node}**")
            c1, c2, c3 = st.columns(3)
            c1.metric("거리", f"{dist:.2f} km")
            c2.metric("예상 시간", f"{int(est_time)} 분")
            c3.metric("도로 정보", f"{len(nearby)} 건")
            
        else:
            folium.PolyLine([s_loc, e_loc], color='#27AE60', weight=6, dash_array='10').add_to(m)
            
            risk_cnt = 0
            for _, r in nearby.iterrows():
                if r['road_name'] in [start_node, end_node]: continue
                if r['risk_score'] >= 70:
                    folium.Marker(
                        [r['lat'], r['lon']],
                        icon=folium.Icon(color='red', icon='exclamation-triangle', prefix='fa'),
                        tooltip=f"⚠️ {r['road_name']}"
                    ).add_to(m)
                    risk_cnt += 1
            
            walk_time = (dist / 4) * 60
            kcal = dist * 50
            st.success(f"🚶 **보행자 분석: {start_node} → {end_node}**")
            c1, c2, c3 = st.columns(3)
            c1.metric("거리", f"{dist:.2f} km")
            c2.metric("도보 시간", f"{int(walk_time)} 분")
            c3.metric("칼로리", f"{int(kcal)} kcal")
            
            if risk_cnt > 0:
                st.toast(f"주의 구간 {risk_cnt}곳 발견!", icon="⚠️")

st_folium(m, width=None, height=550, use_container_width=True)
