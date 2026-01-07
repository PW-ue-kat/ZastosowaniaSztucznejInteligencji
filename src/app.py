import streamlit as st
from langchain_ollama import OllamaLLM
import plotly.express as px
import pandas as pd
import json
import re

# --- KONFIGURACJA MODELU ---
# Używamy modelu Llama3 działającego lokalnie przez Ollama
llm = OllamaLLM(model="llama3.1", temperature=0.1) # Temperatura 0.1 dla większej precyzji

# --- BAZA WIEDZY O ETF-ach (HARDCODED CONTEXT) ---
ETF_MENU = """
MENU DOSTĘPNYCH ETF-ów (Używaj TYLKO tych tickerów):
- SWDA (Akcje Rynki Rozwinięte - Global)
- EMIM (Akcje Rynki Wschodzące)
- VUSA (Akcje USA S&P 500)
- EUNA (Obligacje Rządowe Globalne - Bezpieczne)
- CORP (Obligacje Korporacyjne - Średnie ryzyko)
- QDVE (Nowe Technologie USA - Agresywne)
- SGLN (Złoto fizyczne - Zabezpieczenie)
"""


# --- FUNKCJE POMOCNICZE (PYTHON) ---

def get_investor_summary(age, risk_profile, horizon):
    """Generuje krótką charakterystykę w Pythonie (bez użycia LLM)."""
    summary = f"Inwestor w wieku {age} lat."

    if age < 35:
        stage = "Na etapie akumulacji kapitału, z długim horyzontem czasowym."
    elif age < 55:
        stage = "W środkowej fazie kariery, równoważący wzrost z bezpieczeństwem."
    else:
        stage = "Zbliżający się do wieku emerytalnego, priorytetem jest ochrona kapitału."

    risk_desc = f"Zadeklarowany profil ryzyka: **{risk_profile}**."

    return f"{summary} {stage} {risk_desc} Horyzont inwestycyjny: {horizon.lower()}."


def generate_structured_strategy(age, horizon, risk_profile, amount, goal):
    """
    Wysyła prompt do LLM wymuszając ustrukturyzowaną odpowiedź (JSON + Tekst).
    """

    # Ten separator pomoże nam oddzielić dane dla wykresu od tekstu dla człowieka
    SEPARATOR = "###---SEPARATOR_DANYCH---###"

    prompt = f"""
    Jesteś profesjonalnym robo-doradcą. Twoim zadaniem jest stworzenie strategii portfelowej ETF.
    Musisz wygenerować odpowiedź w DOKŁADNIE dwóch częściach oddzielonych separatorem.

    PROFIL UŻYTKOWNIKA: Wiek: {age}, Horyzont: {horizon}, Ryzyko: {risk_profile}, Cel: {goal}.
    DOSTĘPNE INSTRUMENTY: {ETF_MENU}

    INSTRUKCJE FORMATOWANIA (BARDZO WAŻNE):
    1. Najpierw wygeneruj poprawny obiekt JSON zawierający listę składników portfela. Suma procentów MUSI wynosić 100.
    Format JSON ma wyglądać tak:
    [
        {{"ticker": "SYMBOL1", "percentage": 60, "name": "Krótka nazwa 1"}},
        {{"ticker": "SYMBOL2", "percentage": 40, "name": "Krótka nazwa 2"}}
    ]
    2. Następnie wstaw separator: {SEPARATOR}
    3. Po separatorze napisz szczegółowe uzasadnienie strategii w języku polskim (Markdown). Wyjaśnij, dlaczego dobrałeś takie wagi dla tego konkretnego profilu ryzyka i wieku.

    TWOJA ODPOWIEDŹ (JSON, potem SEPARATOR, potem Tekst):
    """

    # W tej wersji nie używamy streamingu (.stream), potrzebujemy całej odpowiedzi naraz,
    # aby móc ją poprawnie podzielić i przetworzyć JSON.
    return llm.invoke(prompt)


# --- INTERFEJS GRAFICZNY (STREAMLIT) ---

st.set_page_config(page_title="AI Robo-Advisor v3", layout="wide")

# Nagłówek
col_icon, col_header = st.columns([1, 5])
with col_icon:
    st.image("https://cdn-icons-png.flaticon.com/512/4712/4712109.png", width=80)
with col_header:
    st.title("Robo-Doradca: Wizualizacja Strategii")
    st.caption("Powered by local Llama 3 & RTX GPU")

st.markdown("---")

# Lewa kolumna - Ankieta
with st.sidebar:
    st.header("1. Twoje Dane")
    age = st.slider("Wiek", 18, 80, 30)
    amount = st.number_input("Kwota inwestycji (PLN)", 1000, 1000000, 25000, step=5000)
    horizon = st.selectbox("Horyzont", ("Krótki (do 3 lat)", "Średni (3-10 lat)", "Długi (10+ lat)"))
    risk_profile = st.select_slider("Profil Ryzyka",
                                    options=["Konserwatywny", "Umiarkowany", "Dynamiczny", "Agresywny"])
    goal = st.text_input("Cel", "Emerytura / Budowa majątku")

    st.markdown("---")
    generate_btn = st.button("🚀 Generuj Portfel i Wykres", type="primary")

# Prawa kolumna - Wyniki
if generate_btn:
    # 1. Charakterystyka Inwestora
    st.header("2. Analiza Profilu")
    investor_summary = get_investor_summary(age, risk_profile, horizon)
    st.info(investor_summary, icon="👤")

    # 2. Generowanie Strategii
    st.header("3. Proponowana Alokacja Aktywów")

    with st.spinner('Model AI analizuje dane i buduje portfel...'):
        full_response = generate_structured_strategy(age, horizon, risk_profile, amount, goal)

        SEPARATOR = "###---SEPARATOR_DANYCH---###"

        # Zmienne na wyniki, żeby były dostępne poza blokiem try
        json_part = ""
        text_reasoning = ""

        try:
            # KROK 1: Podział na JSON i Tekst (jeśli separator istnieje)
            if SEPARATOR in full_response:
                parts = full_response.split(SEPARATOR)
                raw_json_part = parts[0]
                text_reasoning = parts[1].strip()
            else:
                # Jeśli model zapomniał separatora, szukamy JSONa w całej odpowiedzi
                raw_json_part = full_response
                text_reasoning = "Model nie oddzielił wyraźnie uzasadnienia, ale wykres został wygenerowany."

            # KROK 2: Chirurgiczne wycięcie JSONa (NAPRAWA BŁĘDU)
            # Szukamy fragmentu od pierwszego '[' do ostatniego ']'
            match = re.search(r'\[.*\]', raw_json_part, re.DOTALL)

            if match:
                clean_json = match.group(0)

                # --- POPRAWKA BŁĘDU S&P 500 ---
                # Usuwamy błędne escape'owanie ampersandów (zamiana "\&" na "&")
                # Llama lubi pisać "S\&P 500", co psuje JSON.
                clean_json = clean_json.replace(r'\&', '&')

                # Opcjonalnie: naprawiamy też inne częste błędy (np. \%)
                clean_json = clean_json.replace(r'\%', '%')

                portfolio_data = json.loads(clean_json)

                # --- WIZUALIZACJA ---
                df = pd.DataFrame(portfolio_data)
                df['Wartość PLN'] = (df['percentage'] / 100 * amount).round(2)

                fig = px.pie(
                    df,
                    values='percentage',
                    names='ticker',
                    title=f'Struktura Portfela ({risk_profile})',
                    hover_data=['name', 'Wartość PLN'],
                    labels={'percentage': 'Udział %'},
                    hole=0.4
                )
                fig.update_traces(textposition='inside', textinfo='percent+label')

                col_chart, col_table = st.columns([3, 2])
                with col_chart:
                    st.plotly_chart(fig, use_container_width=True)
                with col_table:
                    st.subheader("Szczegóły:")
                    st.dataframe(df[['ticker', 'percentage', 'Wartość PLN']].set_index('ticker'),
                                 use_container_width=True)

            else:
                st.error("Nie znaleziono danych JSON w odpowiedzi modelu.")
                st.warning("Surowa odpowiedź modelu (do debugowania):")
                st.code(full_response)

            # --- UZASADNIENIE ---
            st.header("4. Uzasadnienie Strategii (AI)")
            if text_reasoning:
                st.markdown(text_reasoning)
            else:
                # Jeśli separator nie zadziałał, spróbujmy wyświetlić wszystko co jest po JSONie
                if match:
                    remaining_text = raw_json_part.replace(match.group(0), "").strip()
                    st.markdown(remaining_text)

        except json.JSONDecodeError as e:
            st.error(f"Błąd parsowania JSON. Model pomylił składnię.")
            st.text(f"Szczegóły: {e}")
            st.code(raw_json_part)

        except Exception as e:
            st.error(f"Wystąpił nieoczekiwany błąd: {e}")

else:
    st.image(
        "https://cdni.iconscout.com/illustration/premium/thumb/robo-advisor-illustration-download-in-svg-png-gif-file-formats--robot-advice-business-finance-investment-pack-illustrations-3762895.png?f=webp",
        width=400)
    st.markdown("### Wypełnij dane po lewej stronie i kliknij 'Generuj', aby rozpocząć symulację.")