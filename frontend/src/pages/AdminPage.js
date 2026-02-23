import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { 
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow 
} from '../components/ui/table';
import { 
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue 
} from '../components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Skeleton } from '../components/ui/skeleton';
import { format } from 'date-fns';
import { ru } from 'date-fns/locale';
import { 
  ArrowLeft, Package, Clock, CheckCircle, Truck, XCircle, 
  Download, Search, RefreshCw, Users, LogOut, DollarSign,
  Settings, ChevronDown
} from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '../components/ui/dropdown-menu';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const STATUS_OPTIONS = [
  { id: 'new', label: 'Новый', icon: Package, color: 'bg-slate-100 text-slate-800' },
  { id: 'in_progress', label: 'В работе', icon: Clock, color: 'bg-amber-100 text-amber-800' },
  { id: 'ready', label: 'Готов', icon: CheckCircle, color: 'bg-green-100 text-green-800' },
  { id: 'delivered', label: 'Выдан', icon: Truck, color: 'bg-blue-100 text-blue-800' },
  { id: 'cancelled', label: 'Отменён', icon: XCircle, color: 'bg-red-100 text-red-800' },
];

const AdminPage = () => {
  const { user, logout, isAdmin } = useAuth();
  const navigate = useNavigate();
  const [orders, setOrders] = useState([]);
  const [users, setUsers] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [activeTab, setActiveTab] = useState('orders');

  useEffect(() => {
    if (!isAdmin) {
      navigate('/');
      return;
    }
    fetchData();
  }, [isAdmin, navigate]);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [ordersRes, statsRes, usersRes] = await Promise.all([
        axios.get(`${API}/admin/orders`),
        axios.get(`${API}/admin/stats`),
        axios.get(`${API}/admin/users`),
      ]);
      setOrders(ordersRes.data);
      setStats(statsRes.data);
      setUsers(usersRes.data);
    } catch (err) {
      toast.error('Ошибка загрузки данных');
    } finally {
      setLoading(false);
    }
  };

  const updateOrderStatus = async (orderId, newStatus) => {
    try {
      await axios.put(`${API}/admin/orders/${orderId}/status`, { status: newStatus });
      toast.success('Статус обновлён');
      fetchData();
    } catch (err) {
      toast.error('Ошибка обновления статуса');
    }
  };

  const toggleUserAdmin = async (userId) => {
    try {
      const res = await axios.put(`${API}/admin/users/${userId}/admin`);
      toast.success(res.data.is_admin ? 'Права администратора выданы' : 'Права администратора отозваны');
      fetchData();
    } catch (err) {
      toast.error('Ошибка изменения прав');
    }
  };

  const exportToSheets = async () => {
    try {
      const res = await axios.post(`${API}/admin/export/sheets`);
      
      // Convert to CSV
      const csv = res.data.rows.map(row => row.join('\t')).join('\n');
      const blob = new Blob([csv], { type: 'text/tab-separated-values;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `orders_${format(new Date(), 'yyyy-MM-dd')}.tsv`;
      link.click();
      
      toast.success(`Экспортировано ${res.data.total_orders} заказов`);
    } catch (err) {
      toast.error('Ошибка экспорта');
    }
  };

  const filteredOrders = orders.filter(order => {
    const matchesStatus = statusFilter === 'all' || order.status === statusFilter;
    const matchesSearch = !searchQuery || 
      order.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      order.user_name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      order.contact_phone?.includes(searchQuery);
    return matchesStatus && matchesSearch;
  });

  const handleLogout = () => {
    logout();
    window.location.href = '/';
  };

  const getStatusBadge = (status) => {
    const statusConfig = STATUS_OPTIONS.find(s => s.id === status);
    return statusConfig ? (
      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${statusConfig.color}`}>
        {statusConfig.label}
      </span>
    ) : status;
  };

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link to="/">
              <Button variant="ghost" size="sm" data-testid="back-to-form">
                <ArrowLeft className="h-4 w-4 mr-2" />
                К форме
              </Button>
            </Link>
            <div>
              <h1 className="text-xl font-bold text-slate-900 tracking-tight">Панель администратора</h1>
              <p className="text-sm text-slate-500">{user?.name}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Button variant="outline" size="sm" onClick={fetchData} data-testid="refresh-btn">
              <RefreshCw className="h-4 w-4" />
            </Button>
            <Button variant="outline" size="sm" onClick={handleLogout} data-testid="admin-logout">
              <LogOut className="h-4 w-4 mr-2" />
              Выйти
            </Button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-8">
        {/* Stats Cards */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 mb-8">
            <Card className="border-slate-200">
              <CardContent className="p-4">
                <div className="text-2xl font-bold text-slate-900">{stats.total_orders}</div>
                <div className="text-sm text-slate-500">Всего заказов</div>
              </CardContent>
            </Card>
            <Card className="border-slate-200 bg-slate-50">
              <CardContent className="p-4">
                <div className="text-2xl font-bold text-slate-600">{stats.new_orders}</div>
                <div className="text-sm text-slate-500">Новых</div>
              </CardContent>
            </Card>
            <Card className="border-slate-200 bg-amber-50">
              <CardContent className="p-4">
                <div className="text-2xl font-bold text-amber-600">{stats.in_progress}</div>
                <div className="text-sm text-slate-500">В работе</div>
              </CardContent>
            </Card>
            <Card className="border-slate-200 bg-green-50">
              <CardContent className="p-4">
                <div className="text-2xl font-bold text-green-600">{stats.ready}</div>
                <div className="text-sm text-slate-500">Готовы</div>
              </CardContent>
            </Card>
            <Card className="border-slate-200 bg-blue-50">
              <CardContent className="p-4">
                <div className="text-2xl font-bold text-blue-600">{stats.delivered}</div>
                <div className="text-sm text-slate-500">Выдано</div>
              </CardContent>
            </Card>
            <Card className="border-slate-200">
              <CardContent className="p-4">
                <div className="text-2xl font-bold text-green-600 font-mono">
                  {stats.revenue.toLocaleString()} ₽
                </div>
                <div className="text-sm text-slate-500">Выручка</div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
          <div className="flex items-center justify-between">
            <TabsList>
              <TabsTrigger value="orders" data-testid="tab-orders">
                <Package className="h-4 w-4 mr-2" />
                Заказы
              </TabsTrigger>
              <TabsTrigger value="users" data-testid="tab-users">
                <Users className="h-4 w-4 mr-2" />
                Пользователи
              </TabsTrigger>
            </TabsList>

            {activeTab === 'orders' && (
              <div className="flex items-center gap-3">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                  <Input
                    placeholder="Поиск по ID, имени, телефону..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-10 w-64 h-10 bg-white"
                    data-testid="search-orders"
                  />
                </div>
                <Select value={statusFilter} onValueChange={setStatusFilter}>
                  <SelectTrigger className="w-40 h-10 bg-white" data-testid="status-filter">
                    <SelectValue placeholder="Статус" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Все статусы</SelectItem>
                    {STATUS_OPTIONS.map((s) => (
                      <SelectItem key={s.id} value={s.id}>{s.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button onClick={exportToSheets} className="bg-green-600 hover:bg-green-700" data-testid="export-btn">
                  <Download className="h-4 w-4 mr-2" />
                  Экспорт
                </Button>
              </div>
            )}
          </div>

          {/* Orders Tab */}
          <TabsContent value="orders" className="mt-0">
            <Card className="border-slate-200">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-24">ID</TableHead>
                      <TableHead>Дата</TableHead>
                      <TableHead>Клиент</TableHead>
                      <TableHead>Телефон</TableHead>
                      <TableHead>Позиции</TableHead>
                      <TableHead>Сумма</TableHead>
                      <TableHead>Дата готовности</TableHead>
                      <TableHead>Статус</TableHead>
                      <TableHead className="w-24">Действия</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {loading ? (
                      Array.from({ length: 5 }).map((_, i) => (
                        <TableRow key={i}>
                          {Array.from({ length: 9 }).map((_, j) => (
                            <TableCell key={j}><Skeleton className="h-5 w-full" /></TableCell>
                          ))}
                        </TableRow>
                      ))
                    ) : filteredOrders.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={9} className="text-center py-8 text-slate-500">
                          Заказов не найдено
                        </TableCell>
                      </TableRow>
                    ) : (
                      filteredOrders.map((order) => (
                        <TableRow key={order.id} data-testid={`order-row-${order.id.slice(0, 8)}`}>
                          <TableCell className="font-mono text-sm">{order.id.slice(0, 8)}</TableCell>
                          <TableCell className="text-sm">
                            {format(new Date(order.created_at), 'dd.MM.yy HH:mm')}
                          </TableCell>
                          <TableCell className="font-medium">{order.user_name || '-'}</TableCell>
                          <TableCell className="text-sm">{order.contact_phone || order.user_phone}</TableCell>
                          <TableCell>
                            <div className="text-sm">
                              {order.items.map((item, idx) => (
                                <div key={idx} className="text-slate-600">
                                  {item.width}×{item.height} × {item.quantity}
                                </div>
                              ))}
                            </div>
                          </TableCell>
                          <TableCell className="font-mono font-medium">
                            {order.total_price.toLocaleString()} ₽
                          </TableCell>
                          <TableCell className="text-sm">{order.desired_date}</TableCell>
                          <TableCell>{getStatusBadge(order.status)}</TableCell>
                          <TableCell>
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <Button variant="outline" size="sm" data-testid={`status-dropdown-${order.id.slice(0, 8)}`}>
                                  <ChevronDown className="h-4 w-4" />
                                </Button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align="end">
                                {STATUS_OPTIONS.map((s) => (
                                  <DropdownMenuItem
                                    key={s.id}
                                    onClick={() => updateOrderStatus(order.id, s.id)}
                                    disabled={order.status === s.id}
                                  >
                                    <s.icon className="h-4 w-4 mr-2" />
                                    {s.label}
                                  </DropdownMenuItem>
                                ))}
                              </DropdownMenuContent>
                            </DropdownMenu>
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            </Card>
          </TabsContent>

          {/* Users Tab */}
          <TabsContent value="users" className="mt-0">
            <Card className="border-slate-200">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Имя</TableHead>
                      <TableHead>Телефон</TableHead>
                      <TableHead>Telegram ID</TableHead>
                      <TableHead>Дата регистрации</TableHead>
                      <TableHead>Администратор</TableHead>
                      <TableHead>Действия</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {loading ? (
                      Array.from({ length: 5 }).map((_, i) => (
                        <TableRow key={i}>
                          {Array.from({ length: 6 }).map((_, j) => (
                            <TableCell key={j}><Skeleton className="h-5 w-full" /></TableCell>
                          ))}
                        </TableRow>
                      ))
                    ) : users.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6} className="text-center py-8 text-slate-500">
                          Пользователей не найдено
                        </TableCell>
                      </TableRow>
                    ) : (
                      users.map((u) => (
                        <TableRow key={u.id}>
                          <TableCell className="font-medium">{u.name}</TableCell>
                          <TableCell className="text-sm">{u.phone}</TableCell>
                          <TableCell className="font-mono text-sm">{u.telegram_id || '-'}</TableCell>
                          <TableCell className="text-sm">
                            {format(new Date(u.created_at), 'dd.MM.yyyy')}
                          </TableCell>
                          <TableCell>
                            {u.is_admin ? (
                              <Badge className="bg-blue-100 text-blue-800">Да</Badge>
                            ) : (
                              <Badge variant="outline">Нет</Badge>
                            )}
                          </TableCell>
                          <TableCell>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => toggleUserAdmin(u.id)}
                              disabled={u.phone === 'admin'}
                              data-testid={`toggle-admin-${u.id.slice(0, 8)}`}
                            >
                              {u.is_admin ? 'Снять права' : 'Сделать админом'}
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            </Card>
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
};

export default AdminPage;
