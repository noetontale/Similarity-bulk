import streamlit as st
import pandas as pd
import requests
import os
import io
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()
api_key = os.getenv("VALUE_SERP_API_KEY")

# Fonction pour nettoyer les URLs en enlevant les paramètres après 'srsltid'
def clean_url(url):
    return url.split('?srsltid=')[0]

# Fonction pour récupérer les URLs des résultats Value SERP pour un mot-clé donné
def get_value_serp_urls(query):
    params = {
        'api_key': api_key,
        'q': query,
        'gl': 'fr',
        'google_domain': 'google.fr'
    }
    # Effectuer la requête HTTP GET à VALUE SERP
    api_result = requests.get('https://api.valueserp.com/search', params=params)
    if api_result.status_code == 200:
        results = api_result.json().get('organic_results', [])[:10]
        return set(clean_url(result['link']) for result in results if 'link' in result)
    else:
        return set()

# Fonction pour comparer les URLs de deux mots-clés
def calculate_similarity(urls1, urls2):
    similar_urls_count = len(urls1.intersection(urls2))
    similarity_percentage = (similar_urls_count / 10) * 100  # Basé sur un total de 10 résultats
    return round(similarity_percentage, 2)

# Fonction principale pour traiter les mots-clés en parallèle
def process_keywords(keywords_df):
    # Obtenir toutes les SERPs en parallèle
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(get_value_serp_urls, keywords_df['Keyword']))
    
    # Créer une colonne pour chaque mot-clé, puis remplir la similarité
    similarity_matrix = pd.DataFrame(index=keywords_df['Keyword'], columns=keywords_df['Keyword'])
    
    for i, (keyword1, urls1) in enumerate(zip(keywords_df['Keyword'], results)):
        for j, (keyword2, urls2) in enumerate(zip(keywords_df['Keyword'], results)):
            if i < j:  # Comparer chaque paire une seule fois
                similarity_percentage = calculate_similarity(urls1, urls2)
                similarity_matrix.loc[keyword1, keyword2] = similarity_percentage
                similarity_matrix.loc[keyword2, keyword1] = similarity_percentage  # Symétrie

    # Créer un tableau formaté avec mots-clés similaires > 10%
    summary_data = []
    for keyword, urls, volume in zip(keywords_df['Keyword'], results, keywords_df['Volume']):
        similar_keywords = []
        for other_keyword in keywords_df['Keyword']:
            if other_keyword != keyword and pd.notna(similarity_matrix.loc[keyword, other_keyword]) and similarity_matrix.loc[keyword, other_keyword] > 10:
                other_volume = keywords_df[keywords_df['Keyword'] == other_keyword]['Volume'].values[0]
                # Formatage avec deux décimales et un espace avant %
                formatted_percentage = f"{similarity_matrix.loc[keyword, other_keyword]:.2f} %"
                similar_keywords.append(f"{other_keyword} ({other_volume}): {formatted_percentage}")
        
        # Ajouter une entrée avec une colonne vide si aucun mot-clé similaire n'est trouvé > 10%
        summary_data.append([keyword, volume, " | ".join(similar_keywords) if similar_keywords else ""])
    
    # Créer le DataFrame final avec les nouvelles colonnes demandées
    summary_df = pd.DataFrame(summary_data, columns=["Mot-clé", "Vol. mensuel", "Liste MC et %"])
    return summary_df

# Interface Streamlit
st.title("Analyse de similarité des SERPs pour une grande liste de mots-clés")

uploaded_file = st.file_uploader("Téléchargez un fichier Excel avec vos mots-clés et volumes (deux colonnes : 'Keyword' et 'Volume')", type=["xlsx"])

if uploaded_file:
    keywords_df = pd.read_excel(uploaded_file)

    if api_key:
        st.write("Récupération des URLs et calcul de similarité...")

        # Calculer la similarité
        summary_df = process_keywords(keywords_df)

        # Sauvegarder le DataFrame en Excel pour le téléchargement
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            summary_df.to_excel(writer, index=False, sheet_name='Résultats')
        output.seek(0)

        # Créer un bouton de téléchargement
        st.download_button(
            label="Télécharger le tableau en Excel",
            data=output,
            file_name="resultats_similarite_keywords.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.error("Veuillez vérifier votre clé API.")
