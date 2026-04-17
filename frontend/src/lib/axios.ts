import axios from 'axios';

const axiosInstance = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:3001/api/v1',
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Interceptor para tratamento global de erros (opcional)
axiosInstance.interceptors.response.use(
  (response) => response,
  (error) => {
    // Aqui podemos tratar 401 (Unauthorized) redirecionando para login
    return Promise.reject(error);
  }
);

export default axiosInstance;
