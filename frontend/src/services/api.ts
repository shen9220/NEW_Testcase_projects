import axios from 'axios';
import { message } from 'antd';

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 180000, // 3 minutes for AI generation
});

api.interceptors.response.use(
  (res) => {
    const body = res.data;
    if (body.code !== undefined && body.code !== 200) {
      message.error(body.message || '请求失败');
      return Promise.reject(new Error(body.message));
    }
    return body;
  },
  (error) => {
    if (error.response?.status === 503) {
      message.warning('Supabase 不可用，已切换到本地存储模式');
    } else if (error.response?.status === 422) {
      message.error('PRD 信息不足，无法生成用例');
    } else if (error.code === 'ECONNABORTED') {
      message.error('请求超时，请重试');
    } else if (!error.response) {
      message.error('后端服务未连接');
    } else {
      message.error(error.response?.data?.detail || error.message || '请求失败');
    }
    return Promise.reject(error);
  }
);

export default api;
