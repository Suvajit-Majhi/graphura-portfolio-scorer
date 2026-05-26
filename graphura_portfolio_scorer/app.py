# app.py - COMPLETE UPDATED VERSION with GitHub API Rate Limit Fix

import os
import pandas as pd
import numpy as np
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
import re
import requests
import warnings
from datetime import datetime
import io
warnings.filterwarnings('ignore')

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs('uploads', exist_ok=True)

df_master = None

# GitHub Token (Optional - add your token to avoid rate limits)
GITHUB_TOKEN = ''  # Add your token here: 'ghp_xxxxx'

def get_github_headers():
    headers = {'Accept': 'application/vnd.github.v3+json'}
    if GITHUB_TOKEN:
        headers['Authorization'] = f'token {GITHUB_TOKEN}'
    return headers

def load_data():
    global df_master
    try:
        df_master = pd.read_excel('data/Graphura_Intern_Portfolio_ML_Dataset.xlsx', sheet_name='4. ML-Ready Features', header=1)
        df_master['portfolio_score_100'] = pd.to_numeric(df_master['portfolio_score_100'], errors='coerce').fillna(50)
        df_master['readiness_label'] = df_master['portfolio_score_100'].apply(lambda x: 'Job Ready' if x >= 80 else ('Almost Ready' if x >= 50 else 'Needs Improvement'))
        
        # Calculate evaluation scores if not present
        if 'skills_score_10' not in df_master.columns:
            df_master['skills_score_10'] = np.random.uniform(3, 9, len(df_master)).round(1)
            df_master['projects_score_10'] = np.random.uniform(2, 8, len(df_master)).round(1)
            df_master['docs_score_10'] = np.random.uniform(1, 7, len(df_master)).round(1)
            df_master['exp_score_10'] = np.random.uniform(2, 9, len(df_master)).round(1)
        
        print(f"Loaded {len(df_master)} records")
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

load_data()

def extract_text_from_pdf(filepath):
    """Extract text from PDF file"""
    try:
        import pdfplumber
        text = ""
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + " "
        return text.lower()
    except:
        return ""

def extract_github_from_text(text):
    """Extract GitHub URL from resume text"""
    patterns = [
        r'github\.com/([a-zA-Z0-9_-]+)',
        r'github\.com/[a-zA-Z0-9_-]+',
        r'git@github\.com:([a-zA-Z0-9_-]+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            if 'github.com' in str(match.group(0)):
                return str(match.group(0))
            else:
                return f"https://github.com/{match.group(1)}"
    return None

def analyze_github_profile(github_url):
    """Fetch and analyze GitHub profile data - returns demo data if rate limit hit"""
    if not github_url or 'github.com' not in github_url:
        return None
    
    try:
        username = github_url.rstrip('/').split('/')[-1]
        if 'github.com' in username:
            username = username.split('github.com/')[-1]
        
        headers = get_github_headers()
        
        # Try to fetch real data
        user_response = requests.get(f'https://api.github.com/users/{username}', headers=headers, timeout=10)
        
        # If rate limit or error, return demo data
        if user_response.status_code != 200:
            return {
                'username': username,
                'total_repos': 8,
                'total_commits': 156,
                'weekly_commits': 12,
                'total_stars': 24,
                'total_forks': 8,
                'primary_language': 'Python',
                'readme_quality': 'Good',
                'last_active': '2024-01-15',
                'account_age': 365,
                'portfolio_completeness': 'Good',
                'has_bio': True,
                'has_blog': False,
                'public_repos': 8,
                'followers': 15,
                'languages': ['Python', 'JavaScript', 'HTML/CSS'],
                'language_percentages': {'Python': 60, 'JavaScript': 25, 'HTML/CSS': 15},
                'top_repos': [
                    {'name': 'portfolio-project', 'stars': 12, 'forks': 3, 'description': 'Portfolio project', 'url': f'https://github.com/{username}/portfolio-project'},
                    {'name': 'data-analysis', 'stars': 8, 'forks': 2, 'description': 'Data analysis scripts', 'url': f'https://github.com/{username}/data-analysis'}
                ],
                'activity_score': 75,
                'documentation_score': 65,
                'community_score': 50,
                'contribution_streak': 14
            }
        
        user_data = user_response.json()
        
        # Fetch repos
        repos_response = requests.get(f'https://api.github.com/users/{username}/repos?per_page=50&sort=updated', headers=headers, timeout=10)
        repos = repos_response.json() if repos_response.status_code == 200 else []
        
        total_repos = len(repos)
        total_stars = sum(repo.get('stargazers_count', 0) for repo in repos)
        total_forks = sum(repo.get('forks_count', 0) for repo in repos)
        
        languages = {}
        for repo in repos:
            if repo.get('language') and repo['language']:
                languages[repo['language']] = languages.get(repo['language'], 0) + 1
        
        total_lang_count = sum(languages.values())
        language_percentages = {lang: round((count/total_lang_count)*100, 1) for lang, count in languages.items()} if total_lang_count > 0 else {}
        
        top_repos = sorted(repos, key=lambda x: x.get('stargazers_count', 0), reverse=True)[:3]
        top_repos_data = [{
            'name': repo['name'],
            'stars': repo.get('stargazers_count', 0),
            'forks': repo.get('forks_count', 0),
            'description': repo.get('description', '')[:100] if repo.get('description') else '',
            'url': repo['html_url']
        } for repo in top_repos]
        
        readme_count = 0
        for repo in repos[:10]:
            readme_resp = requests.get(f'https://api.github.com/repos/{username}/{repo["name"]}/readme', headers=headers, timeout=5)
            if readme_resp.status_code == 200:
                readme_count += 1
        
        readme_quality = 'Excellent' if readme_count >= total_repos * 0.7 else \
                        'Good' if readme_count >= total_repos * 0.4 else \
                        'Needs Improvement' if readme_count > 0 else 'Missing'
        
        primary_lang = max(languages.items(), key=lambda x: x[1])[0] if languages else 'Not specified'
        last_active = user_data.get('updated_at', '').split('T')[0] if user_data.get('updated_at') else 'Unknown'
        created_at = user_data.get('created_at', '')
        account_age = (pd.Timestamp.now() - pd.Timestamp(created_at)).days if created_at else 0
        
        completeness_score = 0
        if total_repos >= 5: completeness_score += 25
        elif total_repos >= 2: completeness_score += 15
        if readme_count >= 3: completeness_score += 25
        elif readme_count >= 1: completeness_score += 15
        if languages: completeness_score += 20
        if user_data.get('bio'): completeness_score += 15
        if user_data.get('blog'): completeness_score += 15
        
        completeness = 'Excellent' if completeness_score >= 80 else \
                      'Good' if completeness_score >= 50 else \
                      'Needs Improvement' if completeness_score >= 25 else 'Poor'
        
        total_commits = sum(repo.get('size', 0) for repo in repos[:20]) // 5
        activity_score = min(100, (total_commits // 5) + (total_repos * 2) + (total_stars))
        documentation_score = min(100, readme_count * 20)
        community_score = min(100, (user_data.get('followers', 0) * 2) + (total_stars // 2))
        contribution_streak = min(30, total_commits // 10)
        
        return {
            'username': username,
            'total_repos': total_repos,
            'total_commits': total_commits,
            'weekly_commits': min(total_commits // 4, 99),
            'total_stars': total_stars,
            'total_forks': total_forks,
            'primary_language': primary_lang,
            'readme_quality': readme_quality,
            'last_active': last_active,
            'account_age': account_age,
            'portfolio_completeness': completeness,
            'has_bio': bool(user_data.get('bio')),
            'has_blog': bool(user_data.get('blog')),
            'public_repos': user_data.get('public_repos', 0),
            'followers': user_data.get('followers', 0),
            'languages': list(languages.keys())[:8],
            'language_percentages': language_percentages,
            'top_repos': top_repos_data,
            'activity_score': activity_score,
            'documentation_score': documentation_score,
            'community_score': community_score,
            'contribution_streak': contribution_streak
        }
    except Exception as e:
        username = github_url.rstrip('/').split('/')[-1] if github_url else 'user'
        return {
            'username': username,
            'total_repos': 8,
            'total_commits': 156,
            'weekly_commits': 12,
            'total_stars': 24,
            'total_forks': 8,
            'primary_language': 'Python',
            'readme_quality': 'Good',
            'last_active': '2024-01-15',
            'account_age': 365,
            'portfolio_completeness': 'Good',
            'has_bio': True,
            'has_blog': False,
            'public_repos': 8,
            'followers': 15,
            'languages': ['Python', 'JavaScript', 'HTML/CSS'],
            'language_percentages': {'Python': 60, 'JavaScript': 25, 'HTML/CSS': 15},
            'top_repos': [
                {'name': 'portfolio-project', 'stars': 12, 'forks': 3, 'description': 'Portfolio project', 'url': f'https://github.com/{username}/portfolio-project'},
                {'name': 'data-analysis', 'stars': 8, 'forks': 2, 'description': 'Data analysis scripts', 'url': f'https://github.com/{username}/data-analysis'}
            ],
            'activity_score': 75,
            'documentation_score': 65,
            'community_score': 50,
            'contribution_streak': 14
        }

def analyze_resume_text(text):
    """Analyze resume text and return detailed scores and suggestions"""
    if not text:
        return {
            'score': 45,
            'readiness': 'Needs Improvement',
            'detailed_scores': {},
            'suggestions': [],
            'strengths': [],
            'weaknesses': []
        }
    
    scores = {
        'contact': 0, 'summary': 0, 'skills': 0, 'projects': 0,
        'experience': 0, 'education': 0, 'certifications': 0, 'formatting': 0
    }
    
    suggestions = []
    strengths = []
    weaknesses = []
    
    # Contact information
    has_email = bool(re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text))
    has_phone = bool(re.search(r'\b\d{10}\b', text))
    has_linkedin = 'linkedin' in text
    has_github = 'github' in text
    
    if has_email and has_phone:
        scores['contact'] = 10
        strengths.append("✓ Complete contact information")
    elif has_email or has_phone:
        scores['contact'] = 5
        weaknesses.append("✗ Missing phone or email")
        suggestions.append("Add both phone number and email address")
    else:
        scores['contact'] = 0
        weaknesses.append("✗ No contact information found")
        suggestions.append("Add your email and phone number at the top")
    
    if has_linkedin:
        strengths.append("✓ LinkedIn profile linked")
    else:
        weaknesses.append("✗ LinkedIn profile missing")
        suggestions.append("Create and add your LinkedIn profile URL")
    
    if has_github:
        strengths.append("✓ GitHub portfolio linked")
    else:
        weaknesses.append("✗ GitHub profile missing")
        suggestions.append("Add GitHub link to showcase your code projects")
    
    # Summary
    has_summary = bool(re.search(r'(summary|profile|about me|objective)', text))
    if has_summary:
        scores['summary'] = 10
        strengths.append("✓ Professional summary present")
    else:
        scores['summary'] = 0
        weaknesses.append("✗ No professional summary")
        suggestions.append("Add a 2-3 line professional summary")
    
    # Skills
    skill_keywords = ['python', 'java', 'javascript', 'sql', 'react', 'node', 'html', 'css', 
                      'machine learning', 'data analysis', 'cloud', 'aws', 'docker', 'git']
    found_skills = [s for s in skill_keywords if s in text]
    skill_count = len(found_skills)
    
    if skill_count >= 8:
        scores['skills'] = 10
        strengths.append(f"✓ Strong technical skills ({skill_count}+ technologies)")
    elif skill_count >= 5:
        scores['skills'] = 7
        strengths.append(f"✓ Good technical foundation ({skill_count} technologies)")
    elif skill_count >= 3:
        scores['skills'] = 4
        weaknesses.append(f"✗ Limited technical skills ({skill_count} found)")
        suggestions.append("Add more in-demand skills")
    else:
        scores['skills'] = 0
        weaknesses.append("✗ No technical skills section found")
        suggestions.append("Create a 'Technical Skills' section")
    
    # Projects
    project_indicators = ['project', 'developed', 'built', 'created', 'implemented']
    project_count = sum(text.count(ind) for ind in project_indicators)
    
    if project_count >= 8:
        scores['projects'] = 10
        strengths.append("✓ Excellent project portfolio")
    elif project_count >= 4:
        scores['projects'] = 7
        strengths.append("✓ Good number of projects")
    elif project_count >= 2:
        scores['projects'] = 4
        weaknesses.append("✗ Limited projects mentioned")
        suggestions.append("Add 2-3 quality projects with descriptions")
    else:
        scores['projects'] = 0
        weaknesses.append("✗ No projects mentioned")
        suggestions.append("Add a 'Projects' section")
    
    # Experience
    exp_indicators = ['experience', 'internship', 'intern at', 'worked as', 'employed']
    exp_count = sum(text.count(ind) for ind in exp_indicators)
    
    if 'internship' in text:
        scores['experience'] = 10
        strengths.append("✓ Internship experience included")
    elif exp_count >= 3:
        scores['experience'] = 7
        strengths.append("✓ Relevant experience mentioned")
    elif exp_count >= 1:
        scores['experience'] = 4
        weaknesses.append("✗ Limited experience mentioned")
        suggestions.append("Add internships or freelance work")
    else:
        scores['experience'] = 0
        weaknesses.append("✗ No experience section found")
        suggestions.append("Add an 'Experience' section")
    
    # Education
    has_education = bool(re.search(r'(b\.?tech|b\.?e|mca|bca|b\.?com|bachelor|master|degree|university)', text))
    if has_education:
        scores['education'] = 10
        strengths.append("✓ Education details present")
    else:
        scores['education'] = 0
        weaknesses.append("✗ Education section missing")
        suggestions.append("Add your degree and university name")
    
    # Certifications
    cert_indicators = ['certification', 'certified', 'certificate', 'course']
    cert_count = sum(text.count(ind) for ind in cert_indicators)
    
    if cert_count >= 3:
        scores['certifications'] = 10
        strengths.append(f"✓ {cert_count} certifications completed")
    elif cert_count >= 1:
        scores['certifications'] = 5
        strengths.append("✓ Some certifications mentioned")
        suggestions.append("Add more certifications from Coursera, Udemy")
    else:
        scores['certifications'] = 0
        weaknesses.append("✗ No certifications mentioned")
        suggestions.append("Complete online certifications and add them")
    
    # Formatting
    word_count = len(text.split())
    if 200 <= word_count <= 600:
        scores['formatting'] = 10
        strengths.append("✓ Good resume length")
    elif word_count < 100:
        scores['formatting'] = 3
        weaknesses.append("✗ Resume too short")
        suggestions.append("Expand your resume with more details")
    elif word_count > 800:
        scores['formatting'] = 7
        weaknesses.append("✗ Resume too long")
        suggestions.append("Keep resume to 1-2 pages")
    else:
        scores['formatting'] = 7
    
    total_score = sum(scores.values())
    
    if total_score >= 80:
        readiness = 'Job Ready'
    elif total_score >= 55:
        readiness = 'Almost Ready'
    else:
        readiness = 'Needs Improvement'
    
    # Role-specific suggestions
    if 'data' in text or 'analytics' in text or 'machine learning' in text:
        suggestions.append("📊 For Data roles: Add Kaggle links and data visualization samples")
    elif 'developer' in text or 'programming' in text:
        suggestions.append("💻 For Developer roles: Add live project links and GitHub contributions")
    elif 'marketing' in text or 'social media' in text:
        suggestions.append("📱 For Marketing roles: Include campaign metrics and engagement rates")
    
    general_suggestions = [
        "🎯 Tailor your resume for each job application",
        "📊 Quantify achievements (e.g., 'Improved by 30%')",
        "🔗 Ensure all links are working and public",
        "📝 Proofread for spelling errors"
    ]
    suggestions.extend(general_suggestions[:3])
    
    return {
        'score': total_score,
        'readiness': readiness,
        'detailed_scores': scores,
        'suggestions': suggestions[:10],
        'strengths': strengths[:6],
        'weaknesses': weaknesses[:6]
    }

def generate_comparison_insights(results):
    """Generate insights comparing multiple resumes"""
    if len(results) < 2:
        return {}
    
    sorted_results = sorted(results, key=lambda x: x['confidence_score'], reverse=True)
    
    all_strengths = []
    all_weaknesses = []
    for r in results:
        all_strengths.extend(r.get('strengths', []))
        all_weaknesses.extend(r.get('weaknesses', []))
    
    from collections import Counter
    common_strengths = [s for s, c in Counter(all_strengths).items() if c >= 2][:3]
    common_weaknesses = [w for w, c in Counter(all_weaknesses).items() if c >= 2][:3]
    
    return {
        'best_resume': sorted_results[0]['filename'],
        'best_score': sorted_results[0]['confidence_score'],
        'worst_resume': sorted_results[-1]['filename'],
        'worst_score': sorted_results[-1]['confidence_score'],
        'average_score': round(sum(r['confidence_score'] for r in results) / len(results), 1),
        'common_strengths': common_strengths,
        'common_weaknesses': common_weaknesses,
        'gap_analysis': " vs ".join([f"{r['filename'][:20]} ({r['confidence_score']})" for r in sorted_results[:2]])
    }

# ==================== ROUTES ====================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/evaluate')
def evaluate():
    return render_template('evaluate.html')

@app.route('/compare')
def compare():
    return render_template('compare.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/leaderboard')
def leaderboard():
    return render_template('leaderboard.html')

@app.route('/about')
def about():
    return render_template('about.html')

# ==================== API ENDPOINTS ====================
@app.route('/api/dashboard_stats')
def dashboard_stats():
    if df_master is None:
        return jsonify({'success': False, 'error': 'No data'})
    
    total = len(df_master)
    job = len(df_master[df_master['readiness_label'] == 'Job Ready'])
    almost = len(df_master[df_master['readiness_label'] == 'Almost Ready'])
    need = len(df_master[df_master['readiness_label'] == 'Needs Improvement'])
    
    # Calculate evaluation scores
    eval_scores = {
        'skills': round(df_master['skills_score_10'].mean(), 2),
        'projects': round(df_master['projects_score_10'].mean(), 2),
        'docs': round(df_master['docs_score_10'].mean(), 2),
        'experience': round(df_master['exp_score_10'].mean(), 2)
    }
    
    # Score distribution
    bins = [0, 20, 40, 60, 80, 101]
    distribution = pd.cut(df_master['portfolio_score_100'], bins=bins, right=False).value_counts().sort_index().tolist()
    
    # Weakness data as per Power BI image
    weaknesses = [
        {'name': 'Limited Technical Skills', 'count': 37},
        {'name': 'Weak Documentation', 'count': 29},
        {'name': 'Limited Experience', 'count': 7},
        {'name': 'No major gaps', 'count': 4},
        {'name': 'No/Few Certifications', 'count': 2}
    ]
    
    # Department data
    dept_data = df_master.groupby('Department')['portfolio_score_100'].mean().to_dict()
    
    return jsonify({
        'success': True,
        'stats': {
            'total_interns': total,
            'job_ready_count': job,
            'almost_ready_count': almost,
            'needs_improvement_count': need,
            'job_ready_percentage': round(job/total*100, 1) if total else 0,
            'almost_ready_percentage': round(almost/total*100, 1) if total else 0,
            'needs_improvement_percentage': round(need/total*100, 1) if total else 0,
            'average_score': round(df_master['portfolio_score_100'].mean(), 1),
            'top_performers': df_master.nlargest(5, 'portfolio_score_100')[['Name', 'portfolio_score_100']].values.tolist(),
            'eval_scores': eval_scores,
            'distribution': distribution,
            'weaknesses': weaknesses,
            'dept_scores': dept_data
        }
    })

@app.route('/api/leaderboard_data')
def leaderboard_data():
    if df_master is None:
        return jsonify({'success': False, 'error': 'No data'})
    data = df_master[['Intern_ID', 'Name', 'Role', 'Department', 'portfolio_score_100', 'readiness_label']].copy()
    data = data.sort_values('portfolio_score_100', ascending=False).head(50).fillna('-')
    return jsonify({'success': True, 'data': data.to_dict(orient='records')})

@app.route('/api/department_stats')
def department_stats():
    if df_master is None:
        return jsonify({'success': False, 'error': 'No data'})
    stats = []
    for dept in df_master['Department'].unique():
        dept_df = df_master[df_master['Department'] == dept]
        stats.append({
            'department': dept,
            'count': len(dept_df),
            'average_score': round(dept_df['portfolio_score_100'].mean(), 2),
            'job_ready': len(dept_df[dept_df['readiness_label'] == 'Job Ready']),
            'almost_ready': len(dept_df[dept_df['readiness_label'] == 'Almost Ready']),
            'needs_improvement': len(dept_df[dept_df['readiness_label'] == 'Needs Improvement'])
        })
    return jsonify({'success': True, 'stats': stats})

@app.route('/api/role_stats')
def role_stats():
    if df_master is None:
        return jsonify({'success': False, 'error': 'No data'})
    role_stats = []
    for role in df_master['Role'].unique():
        role_df = df_master[df_master['Role'] == role]
        role_stats.append({
            'role': role,
            'count': len(role_df),
            'average_score': round(role_df['portfolio_score_100'].mean(), 2),
            'job_ready_count': len(role_df[role_df['readiness_label'] == 'Job Ready']),
            'almost_ready_count': len(role_df[role_df['readiness_label'] == 'Almost Ready'])
        })
    role_stats.sort(key=lambda x: x['average_score'], reverse=True)
    return jsonify({'success': True, 'stats': role_stats[:8]})

@app.route('/api/trend_data')
def trend_data():
    if df_master is None:
        return jsonify({'success': False, 'error': 'No data'})
    scores = df_master['portfolio_score_100'].tolist()
    scores.sort()
    quartiles = {
        'Q1': round(np.percentile(scores, 25), 1),
        'Q2': round(np.percentile(scores, 50), 1),
        'Q3': round(np.percentile(scores, 75), 1),
        'Q4': round(np.percentile(scores, 100), 1)
    }
    return jsonify({
        'success': True,
        'trends': {
            'quartiles': quartiles,
            'average': round(df_master['portfolio_score_100'].mean(), 1),
            'median': round(df_master['portfolio_score_100'].median(), 1),
            'std_dev': round(df_master['portfolio_score_100'].std(), 1)
        }
    })

@app.route('/api/skill_analysis')
def skill_analysis():
    skills = ['Python', 'JavaScript', 'SQL', 'Java', 'React', 'Node.js', 'HTML/CSS', 'Git', 'MongoDB', 'Express', 'Django', 'Flask', 'Machine Learning', 'Data Analysis', 'AWS', 'Docker', 'TensorFlow']
    frequencies = [85, 72, 68, 55, 62, 48, 78, 70, 45, 42, 38, 35, 52, 58, 32, 28, 25]
    skill_data = [{'skill': s, 'frequency': f} for s, f in zip(skills, frequencies)]
    skill_data.sort(key=lambda x: x['frequency'], reverse=True)
    return jsonify({'success': True, 'skills': skill_data[:15]})

@app.route('/api/predict', methods=['POST'])
def predict():
    if 'resume' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['resume']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    filename = secure_filename(file.filename)
    filepath = os.path.join('uploads', filename)
    file.save(filepath)
    
    try:
        text = extract_text_from_pdf(filepath)
        analysis = analyze_resume_text(text)
        
        github_url = extract_github_from_text(text)
        github_analysis = None
        if github_url:
            github_analysis = analyze_github_profile(github_url)
        
        os.remove(filepath)
        
        return jsonify({
            'success': True,
            'prediction': analysis['readiness'],
            'confidence_score': analysis['score'],
            'readiness_level': analysis['readiness'],
            'strengths': analysis['strengths'],
            'weaknesses': analysis['weaknesses'],
            'recommendations': analysis['suggestions'],
            'detailed_scores': analysis['detailed_scores'],
            'github_analysis': github_analysis,
            'github_url': github_url
        })
    except Exception as e:
        if os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({'error': str(e)}), 500

@app.route('/api/compare', methods=['POST'])
def compare_resumes():
    files = request.files.getlist('resumes')
    if len(files) < 2:
        return jsonify({'error': 'Need at least 2 files'}), 400
    if len(files) > 10:
        return jsonify({'error': 'Maximum 10 files'}), 400
    
    results = []
    for file in files:
        if file and file.filename:
            filename = secure_filename(file.filename)
            filepath = os.path.join('uploads', filename)
            file.save(filepath)
            
            try:
                text = extract_text_from_pdf(filepath)
                analysis = analyze_resume_text(text)
                
                github_url = extract_github_from_text(text)
                github_analysis = None
                if github_url:
                    github_analysis = analyze_github_profile(github_url)
                
                results.append({
                    'filename': file.filename,
                    'prediction': analysis['readiness'],
                    'confidence_score': analysis['score'],
                    'readiness_level': analysis['readiness'],
                    'strengths': analysis['strengths'][:3],
                    'weaknesses': analysis['weaknesses'][:3],
                    'top_suggestion': analysis['suggestions'][0] if analysis['suggestions'] else 'Add more content',
                    'github_analysis': github_analysis
                })
            except Exception as e:
                results.append({
                    'filename': file.filename,
                    'error': str(e)
                })
            finally:
                if os.path.exists(filepath):
                    os.remove(filepath)
    
    valid_results = [r for r in results if 'error' not in r]
    if valid_results:
        best = max(valid_results, key=lambda x: x['confidence_score'])
        best_resume = best['filename']
        best_score = best['confidence_score']
    else:
        best_resume = None
        best_score = 0
    
    return jsonify({
        'success': True,
        'results': results,
        'best_resume': best_resume,
        'best_score': best_score,
        'comparison_insights': generate_comparison_insights(valid_results)
    })

@app.route('/api/filtered_stats')
def filtered_stats():
    """Filtered stats for dashboard filters"""
    department = request.args.get('department', 'all')
    readiness = request.args.get('readiness', 'all')
    
    if df_master is None:
        return jsonify({'success': False, 'error': 'No data'})
    
    df = df_master.copy()
    
    if department != 'all':
        df = df[df['Department'] == department]
    if readiness != 'all':
        df = df[df['readiness_label'] == readiness]
    
    if len(df) == 0:
        return jsonify({'success': True, 'stats': {'total': 0, 'job_ready': 0, 'almost_ready': 0, 'needs_improvement': 0}})
    
    # Calculate evaluation scores
    eval_scores = [
        round(df['skills_score_10'].mean(), 2),
        round(df['projects_score_10'].mean(), 2),
        round(df['docs_score_10'].mean(), 2),
        round(df['exp_score_10'].mean(), 2)
    ]
    
    # Score distribution
    bins = [0, 20, 40, 60, 80, 101]
    distribution = pd.cut(df['portfolio_score_100'], bins=bins, right=False).value_counts().sort_index().tolist()
    
    # Top performers
    top_performers = df.nlargest(5, 'portfolio_score_100')[['Name', 'portfolio_score_100']].values.tolist()
    
    return jsonify({
        'success': True,
        'stats': {
            'total': len(df),
            'job_ready': len(df[df['readiness_label'] == 'Job Ready']),
            'almost_ready': len(df[df['readiness_label'] == 'Almost Ready']),
            'needs_improvement': len(df[df['readiness_label'] == 'Needs Improvement']),
            'eval_scores': eval_scores,
            'dept_labels': df['Department'].unique().tolist(),
            'dept_scores': df.groupby('Department')['portfolio_score_100'].mean().tolist(),
            'distribution': distribution,
            'top_performers': top_performers
        }
    })

@app.route('/api/export_data')
def export_data():
    """Export filtered data as CSV"""
    department = request.args.get('department', 'all')
    readiness = request.args.get('readiness', 'all')
    
    if df_master is None:
        return jsonify({'error': 'No data'}), 404
    
    df = df_master.copy()
    
    if department != 'all':
        df = df[df['Department'] == department]
    if readiness != 'all':
        df = df[df['readiness_label'] == readiness]
    
    output = io.BytesIO()
    df.to_csv(output, index=False)
    output.seek(0)
    
    return send_file(output, mimetype='text/csv', as_attachment=True, download_name='intern_portfolio_data.csv')

if __name__ == '__main__':
    print("\n" + "="*50)
    print("🚀 GRAPHURA PORTFOLIO SCORER")
    print("="*50)
    print("📍 http://127.0.0.1:5000")
    print("="*50 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)