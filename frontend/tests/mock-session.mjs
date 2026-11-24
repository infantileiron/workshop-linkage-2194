// Mock 会话 store：读写测试入口提供的 sessionStorage。
const key = 'hemu-session';
export const session = () => JSON.parse(sessionStorage.getItem(key));
export const setSession = value => value
  ? sessionStorage.setItem(key, JSON.stringify(value)) : sessionStorage.removeItem(key);
export const canWrite = () => ['manager', 'analyst'].includes(session()?.role);
