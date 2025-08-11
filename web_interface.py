from flask import Flask, render_template, request, jsonify, session
from career_agent import CareerAgent
import json
import os

app = Flask(__name__)
app.secret_key = 'career_agent_secret_key'

# 初始化agent
api_key = "A2hfmVGouQ4OMhibmfZxgFL10OlC0jDk_GPT_AK"
agent = CareerAgent(api_key)

@app.route('/')
def index():
    """主页"""
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    """聊天接口"""
    try:
        data = request.get_json()
        user_message = data.get('message', '')
        user_context = data.get('context', {})
        
        if not user_message:
            return jsonify({'error': '请输入您的问题'})
        
        # 获取agent回复
        response = agent.chat(user_message, user_context)
        
        return jsonify({
            'response': response,
            'status': 'success'
        })
    except Exception as e:
        return jsonify({
            'error': f'处理请求时出现错误: {str(e)}',
            'status': 'error'
        })

@app.route('/job_recommendations', methods=['POST'])
def job_recommendations():
    """岗位推荐接口"""
    try:
        data = request.get_json()
        user_profile = {
            'skills': data.get('skills', []),
            'experience': data.get('experience', ''),
            'location': data.get('location', ''),
            'education': data.get('education', ''),
            'salary_expectation': data.get('salary_expectation', '')
        }
        
        # 获取岗位推荐
        recommendations = agent.get_job_recommendations(user_profile)
        
        return jsonify({
            'recommendations': recommendations,
            'status': 'success'
        })
    except Exception as e:
        return jsonify({
            'error': f'获取岗位推荐时出现错误: {str(e)}',
            'status': 'error'
        })

@app.route('/career_advice', methods=['POST'])
def career_advice():
    """求职建议接口"""
    try:
        data = request.get_json()
        topic = data.get('topic', '')
        
        if not topic:
            return jsonify({'error': '请输入建议主题'})
        
        # 获取求职建议
        advice = agent.get_career_advice(topic)
        
        return jsonify({
            'advice': advice,
            'status': 'success'
        })
    except Exception as e:
        return jsonify({
            'error': f'获取求职建议时出现错误: {str(e)}',
            'status': 'error'
        })

@app.route('/user_profile', methods=['POST'])
def save_user_profile():
    """保存用户档案"""
    try:
        data = request.get_json()
        session['user_profile'] = data
        
        return jsonify({
            'message': '用户档案保存成功',
            'status': 'success'
        })
    except Exception as e:
        return jsonify({
            'error': f'保存用户档案时出现错误: {str(e)}',
            'status': 'error'
        })

@app.route('/user_profile', methods=['GET'])
def get_user_profile():
    """获取用户档案"""
    try:
        profile = session.get('user_profile', {})
        return jsonify({
            'profile': profile,
            'status': 'success'
        })
    except Exception as e:
        return jsonify({
            'error': f'获取用户档案时出现错误: {str(e)}',
            'status': 'error'
        })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000) 