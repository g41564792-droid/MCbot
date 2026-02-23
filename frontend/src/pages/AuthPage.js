import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { toast } from 'sonner';
import { User, Phone, Lock, ArrowRight, Loader2 } from 'lucide-react';

const AuthPage = () => {
  const navigate = useNavigate();
  const { login, register } = useAuth();
  const [loading, setLoading] = useState(false);
  
  // Login state
  const [loginPhone, setLoginPhone] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  
  // Register state
  const [regPhone, setRegPhone] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [regName, setRegName] = useState('');
  const [regTelegram, setRegTelegram] = useState('');

  const handleLogin = async (e) => {
    e.preventDefault();
    if (!loginPhone || !loginPassword) {
      toast.error('Заполните все поля');
      return;
    }
    setLoading(true);
    try {
      const user = await login(loginPhone, loginPassword);
      toast.success('Добро пожаловать!');
      navigate(user.is_admin ? '/admin' : '/');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Ошибка входа');
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    if (!regPhone || !regPassword || !regName) {
      toast.error('Заполните обязательные поля');
      return;
    }
    setLoading(true);
    try {
      await register(regPhone, regPassword, regName, regTelegram);
      toast.success('Регистрация успешна!');
      navigate('/');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Ошибка регистрации');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <div className="w-full max-w-md animate-fade-in">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-slate-900 tracking-tight">Москитные сетки</h1>
          <p className="text-slate-600 mt-2">Система заказов</p>
        </div>
        
        <Card className="border-slate-200 shadow-sm">
          <Tabs defaultValue="login" className="w-full">
            <CardHeader className="pb-4">
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="login" data-testid="tab-login">Вход</TabsTrigger>
                <TabsTrigger value="register" data-testid="tab-register">Регистрация</TabsTrigger>
              </TabsList>
            </CardHeader>
            
            <CardContent>
              <TabsContent value="login" className="mt-0">
                <form onSubmit={handleLogin} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="login-phone">Телефон</Label>
                    <div className="relative">
                      <Phone className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                      <Input
                        id="login-phone"
                        data-testid="login-phone"
                        type="text"
                        placeholder="+7 (999) 123-45-67"
                        value={loginPhone}
                        onChange={(e) => setLoginPhone(e.target.value)}
                        className="pl-10 h-12 bg-slate-50"
                      />
                    </div>
                  </div>
                  
                  <div className="space-y-2">
                    <Label htmlFor="login-password">Пароль</Label>
                    <div className="relative">
                      <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                      <Input
                        id="login-password"
                        data-testid="login-password"
                        type="password"
                        placeholder="••••••••"
                        value={loginPassword}
                        onChange={(e) => setLoginPassword(e.target.value)}
                        className="pl-10 h-12 bg-slate-50"
                      />
                    </div>
                  </div>
                  
                  <Button
                    type="submit"
                    data-testid="login-submit"
                    className="w-full h-12 bg-blue-600 hover:bg-blue-700"
                    disabled={loading}
                  >
                    {loading ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <>Войти <ArrowRight className="ml-2 h-4 w-4" /></>
                    )}
                  </Button>
                </form>
              </TabsContent>
              
              <TabsContent value="register" className="mt-0">
                <form onSubmit={handleRegister} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="reg-name">Имя *</Label>
                    <div className="relative">
                      <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                      <Input
                        id="reg-name"
                        data-testid="reg-name"
                        type="text"
                        placeholder="Иван Иванов"
                        value={regName}
                        onChange={(e) => setRegName(e.target.value)}
                        className="pl-10 h-12 bg-slate-50"
                      />
                    </div>
                  </div>
                  
                  <div className="space-y-2">
                    <Label htmlFor="reg-phone">Телефон *</Label>
                    <div className="relative">
                      <Phone className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                      <Input
                        id="reg-phone"
                        data-testid="reg-phone"
                        type="text"
                        placeholder="+7 (999) 123-45-67"
                        value={regPhone}
                        onChange={(e) => setRegPhone(e.target.value)}
                        className="pl-10 h-12 bg-slate-50"
                      />
                    </div>
                  </div>
                  
                  <div className="space-y-2">
                    <Label htmlFor="reg-password">Пароль *</Label>
                    <div className="relative">
                      <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4" />
                      <Input
                        id="reg-password"
                        data-testid="reg-password"
                        type="password"
                        placeholder="••••••••"
                        value={regPassword}
                        onChange={(e) => setRegPassword(e.target.value)}
                        className="pl-10 h-12 bg-slate-50"
                      />
                    </div>
                  </div>
                  
                  <div className="space-y-2">
                    <Label htmlFor="reg-telegram">Telegram ID (для уведомлений)</Label>
                    <Input
                      id="reg-telegram"
                      data-testid="reg-telegram"
                      type="text"
                      placeholder="123456789"
                      value={regTelegram}
                      onChange={(e) => setRegTelegram(e.target.value)}
                      className="h-12 bg-slate-50"
                    />
                    <p className="text-xs text-slate-500">
                      Получите ID через бота @OlWait_MC_Bot командой /start
                    </p>
                  </div>
                  
                  <Button
                    type="submit"
                    data-testid="register-submit"
                    className="w-full h-12 bg-blue-600 hover:bg-blue-700"
                    disabled={loading}
                  >
                    {loading ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <>Зарегистрироваться <ArrowRight className="ml-2 h-4 w-4" /></>
                    )}
                  </Button>
                </form>
              </TabsContent>
            </CardContent>
          </Tabs>
        </Card>
        
        <p className="text-center text-sm text-slate-500 mt-6">
          <Link to="/" className="text-blue-600 hover:underline">Вернуться на главную</Link>
        </p>
      </div>
    </div>
  );
};

export default AuthPage;
