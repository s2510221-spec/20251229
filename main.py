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
st.set_page_config(layout="wide", page_title="SafeRoad Ultimate")
st.title("🚦 SafeRoad: 안전 경로 시스템 (오류 해결 버전)")
st.markdown("데이터가 자동으로 읽히지 않으면, 아래에서 **직접 설정**할 수 있습니다.")

# ---------------------------------------------------------
# 2. 데이터 로드 (파일 업로드 기능 추가)
# ---------------------------------------------------------
@st.cache_data(show_spinner=False)
def try_load_local_file():
    file_path = '20251229road_최종.csv'
    for enc in ['cp949', 'utf-8', 'euc-kr', 'utf-8-sig']:
        try:
            df = pd.read_csv(file_path, encoding=enc)
            df.columns = df.columns.str.strip()
            return df
        except: continue
    return None

# 1차 시도: 로컬 파일 읽기
df_raw = try_load_local_file()

# 사이드바 설정 영역
st.sidebar.header("📂 데이터 설정")

# 파일이 없거나 읽기 실패 시 -> 파일 업로더 활성화
if df_raw is None:
    st.warning("⚠️ '20251229road_최종.csv' 파일을 찾지 못했습니다. 아래에서 직접 업로드해주세요.")
    uploaded_file = st.sidebar.file_uploader("CSV 파일 업로드", type=['csv'])
    if uploaded_file is not None:
        try:
            df_raw = pd.read_csv(uploaded_file, encoding='cp949') # 1차 시도
        except:
            uploaded_file.seek(0)
            df_raw = pd.read_csv(uploaded_file, encoding='utf-8') # 2차 시도
    else:
        st.stop() # 파일 없으면 여기서 멈춤

# ---------------------------------------------------------
# 3. 컬럼 매핑 (사용자가 직접 선택)
# ---------------------------------------------------------
if df_raw is not None:
    st.sidebar.success("파일 읽기 성공!")
    
    # 컬럼 목록 가져오기
    cols = df_raw.columns.tolist()
    
    # 기본값 추측 헬퍼 함수
    def get_idx(options, keywords):
        for i, opt in enumerate(options):
            if any(k in opt.lower() for k in keywords): return i
        return 0

    st.sidebar.subheader("1. 컬럼 연결하기")
    st.sidebar.caption("지도에 표시할 정확한 컬럼을 선택해주세요.")
    
    col_lat = st.sidebar.selectbox("위도 (Latitude)", cols, index=get_idx(cols, ['lat', '위도']))
    col_lon = st.sidebar.selectbox("경도 (Longitude)", cols, index=get_idx(cols, ['lon', '경도']))
    col_name = st.sidebar.selectbox("장소명 (Name)", cols, index=get_idx(cols, ['name', '명', 'place']))
    col_risk = st.sidebar.selectbox("위험도 (Risk)", cols, index=get_idx(cols, ['risk', '위험', 'score']))

    # 데이터 정제
    try:
        df = df_raw.copy()
        # 숫자 변환 (에러 발생 시 NaN 처리)
        df['lat'] = pd.to_numeric(df[col_lat], errors='coerce')
        df['lon'] = pd.to_numeric(df[col_lon], errors='coerce')
        
        # 좌표 없는 행 삭제
        df = df.dropna(subset=['lat', 'lon'])
        
        # 나머지 데이터 매핑
        df['road_name'] = df[col_name].astype(str)
        df['risk_score'] = pd.to_numeric(df[col_risk], errors='coerce').fillna(50) # 위험도 없으면 50
        
        if df.empty:
            st.error("데이터가 비어있습니다. 위도/경도 컬럼을 올바르게 선택했는지 확인해주세요.")
            st.stop()
            
    except Exception as e:
        st.error(f"데이터 처리 중 오류 발생: {e}")
        st.stop()

    # ---------------------------------------------------------
    # 4. 모드 설정 및 경로 탐색 (기존 로직 유지)
    # ---------------------------------------------------------
    st.sidebar.markdown("---")
    st.sidebar.subheader("2. 경로 탐색")
    
    mode = st.sidebar.radio("이동 모드", ["🚗 자동차 (빠른길)", "🚶 보행자 (안전길)"])
    
    places = sorted(df['road_name'].unique())
    start_node = st.sidebar.selectbox("출발지", places, index=0)
    end_node = st.sidebar.selectbox("도착지", places, index=1 if len(places)>1 else 0)
    
    run_btn = st.sidebar.button("분석 시작")

    # 지도 초기화
    avg_lat, avg_lon = df['lat'].mean(), df['lon'].mean()
    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=11)

    if run_btn:
        if start_node == end_node:
            st.warning("출발지와 도착지가 같습니다.")
        else:
            # 좌표 획득
            s_row = df[df['road_name'] == start_node].iloc[0]
            e_row = df[df['road_name'] == end_node].iloc[0]
            s_loc = [s_row['lat'], s_row['lon']]
            e_loc = [e_row['lat'], e_row['lon']]
            
            # 지도 중심 이동
            m.location = [(s_loc[0]+e_loc[0])/2, (s_loc[1]+e_loc[1])/2]
            m.zoom_start = 13
            
            # 1. 출발/도착 아이콘
            folium.Marker(s_loc, popup="출발", icon=folium.Icon(color='blue', icon='play')).add_to(m)
            folium.Marker(e_loc, popup="도착", icon=folium.Icon(color='red', icon='flag')).add_to(m)
            
            # 거리 계산
            dist = math.sqrt((s_loc[0]-e_loc[0])**2 + (s_loc[1]-e_loc[1])**2) * 111
            
            # 주변 데이터 필터링
            bounds = [
                min(s_loc[0], e_loc[0])-0.02, max(s_loc[0], e_loc[0])+0.02,
                min(s_loc[1], e_loc[1])-0.02, max(s_loc[1], e_loc[1])+0.02
            ]
            nearby = df[
                (df['lat'].between(bounds[0], bounds[1])) & 
                (df['lon'].between(bounds[2], bounds[3]))
            ]
            
            # ==========================================
            # 🚗 vs 🚶 차별화 로직
            # ==========================================
            if "자동차" in mode:
                # [자동차] 파란색 굵은 실선 + 클러스터링(정보 요약)
                folium.PolyLine([s_loc, e_loc], color='#2E86C1', weight=8, opacity=0.8).add_to(m)
                
                cluster = MarkerCluster().add_to(m)
                for _, r in nearby.iterrows():
                    if r['road_name'] in [start_node, end_node]: continue
                    sc = r['risk_score']
                    c = 'green' if sc < 30 else ('orange' if sc < 70 else 'red')
                    folium.CircleMarker(
                        [r['lat'], r['lon']], radius=5, color=c, fill=True, fill_color=c,
                        popup=f"{r['road_name']}({int(sc)})"
                    ).add_to(cluster)
                
                # 결과 패널
                est_time = (dist / 40) * 60
                st.info(f"🚘 **자동차 모드 결과**")
                c1, c2, c3 = st.columns(3)
                c1.metric("거리", f"{dist:.2f} km")
                c2.metric("예상 시간", f"{int(est_time)} 분")
                c3.metric("도로 정보", f"{len(nearby)} 건")
                
            else:
                # [보행자] 초록색 점선 + 위험 구간만 경고(Red)
                folium.PolyLine([s_loc, e_loc], color='#27AE60', weight=5, dash_array='10').add_to(m)
                
                danger_cnt = 0
                for _, r in nearby.iterrows():
                    if r['road_name'] in [start_node, end_node]: continue
                    if r['risk_score'] >= 70: # 위험한 곳만
                        folium.Marker(
                            [r['lat'], r['lon']], 
                            icon=folium.Icon(color='red', icon='exclamation-triangle', prefix='fa'),
                            tooltip=f"⚠️ 주의: {r['road_name']}"
                        ).add_to(m)
                        danger_cnt += 1
                
                # 결과 패널
                walk_time = (dist / 4) * 60
                kcal = dist * 50
                st.success(f"🚶 **보행자 모드 결과**")
                c1, c2, c3 = st.columns(3)
                c1.metric("거리", f"{dist:.2f} km")
                c2.metric("도보 시간", f"{int(walk_time)} 분")
                c3.metric("소모 칼로리", f"{int(kcal)} kcal")
                
                if danger_cnt > 0:
                    st.toast(f"경로상 위험 구간이 {danger_cnt}곳 있습니다!", icon="⚠️")

    # 지도 출력
    st_folium(m, width=None, height=500, use_container_width=True)
