import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Skeleton } from '../components/ui/skeleton';
import { 
  Dialog, DialogContent, DialogDescription, DialogFooter, 
  DialogHeader, DialogTitle 
} from '../components/ui/dialog';
import { format } from 'date-fns';
import { ru } from 'date-fns/locale';
import { QRCodeSVG } from 'qrcode.react';
import { 
  ArrowLeft, Package, Calendar, Phone, FileText, 
  ChevronRight, LogOut, ShoppingCart, Edit, X, MessageCircle
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const TELEGRAM_BOT_URL = 'https://t.me/OlWait_MC_Bot';

const STATUS_LABELS = {
  new: { label: 'Новый', class: 'status-new' },
  in_progress: { label: 'В работе', class: 'status-in_progress' },
  ready: { label: 'Готов', class: 'status-ready' },
  delivered: { label: 'Выдан', class: 'status-delivered' },
  cancelled: { label: 'Отменён', class: 'status-cancelled' },
};

const OrdersPage = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [cancelDialogOpen, setCancelDialogOpen] = useState(false);
  const [orderToCancel, setOrderToCancel] = useState(null);
  const [cancelling, setCancelling] = useState(false);

  useEffect(() => {
    fetchOrders();
  }, []);

  const fetchOrders = async () => {
    try {
      const res = await axios.get(`${API}/orders`);
      setOrders(res.data);
    } catch (err) {
      console.error('Error fetching orders:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    logout();
    window.location.href = '/';
  };

  const handleCancelOrder = async () => {
    if (!orderToCancel) return;
    setCancelling(true);
    try {
      await axios.delete(`${API}/orders/${orderToCancel.id}`);
      toast.success('Заказ отменён');
      fetchOrders();
      setCancelDialogOpen(false);
      setOrderToCancel(null);
      setSelectedOrder(null);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Ошибка отмены заказа');
    } finally {
      setCancelling(false);
    }
  };

  const openCancelDialog = (order, e) => {
    e.stopPropagation();
    setOrderToCancel(order);
    setCancelDialogOpen(true);
  };

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-50">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link to="/">
              <Button variant="ghost" size="sm" data-testid="back-btn">
                <ArrowLeft className="h-4 w-4 mr-2" />
                Назад
              </Button>
            </Link>
            <div>
              <h1 className="text-xl font-bold text-slate-900 tracking-tight">Мои заказы</h1>
              <p className="text-sm text-slate-500">{user?.name}</p>
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={handleLogout} data-testid="logout-btn">
            <LogOut className="h-4 w-4 mr-2" />
            Выйти
          </Button>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-8">
        {/* Telegram QR Code Card */}
        <Card className="border-slate-200 mb-6 bg-gradient-to-r from-blue-50 to-cyan-50">
          <CardContent className="p-6">
            <div className="flex items-center gap-6">
              <div className="bg-white p-3 rounded-xl shadow-sm">
                <QRCodeSVG 
                  value={TELEGRAM_BOT_URL} 
                  size={100}
                  level="M"
                  includeMargin={false}
                />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-2">
                  <MessageCircle className="h-5 w-5 text-blue-600" />
                  <h3 className="font-semibold text-slate-900">Telegram бот</h3>
                </div>
                <p className="text-sm text-slate-600 mb-3">
                  Оформляйте заказы и получайте уведомления о статусе прямо в Telegram
                </p>
                <a 
                  href={TELEGRAM_BOT_URL} 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="inline-flex items-center text-sm text-blue-600 hover:text-blue-700 font-medium"
                >
                  @OlWait_MC_Bot
                  <ChevronRight className="h-4 w-4 ml-1" />
                </a>
              </div>
            </div>
          </CardContent>
        </Card>

        {loading ? (
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <Card key={i} className="border-slate-200">
                <CardContent className="p-6">
                  <div className="flex justify-between items-start">
                    <div className="space-y-2">
                      <Skeleton className="h-5 w-32" />
                      <Skeleton className="h-4 w-48" />
                    </div>
                    <Skeleton className="h-6 w-20" />
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : orders.length === 0 ? (
          <Card className="border-slate-200">
            <CardContent className="p-12 text-center">
              <ShoppingCart className="h-12 w-12 text-slate-300 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-slate-900 mb-2">Заказов пока нет</h3>
              <p className="text-slate-500 mb-6">Оформите первый заказ на москитные сетки</p>
              <Link to="/">
                <Button className="bg-blue-600 hover:bg-blue-700" data-testid="create-order-btn">
                  Создать заказ
                </Button>
              </Link>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-4">
            {orders.map((order) => (
              <Card 
                key={order.id} 
                className={`border-slate-200 cursor-pointer transition-all hover:border-blue-400 hover:shadow-md ${
                  selectedOrder?.id === order.id ? 'border-blue-600 ring-2 ring-blue-600 ring-opacity-50' : ''
                }`}
                onClick={() => setSelectedOrder(selectedOrder?.id === order.id ? null : order)}
                data-testid={`order-card-${order.id.slice(0, 8)}`}
              >
                <CardContent className="p-6">
                  <div className="flex justify-between items-start">
                    <div>
                      <div className="flex items-center gap-3 mb-2">
                        <h3 className="font-semibold text-slate-900 font-mono">
                          #{order.id.slice(0, 8)}
                        </h3>
                        <span className={`status-badge ${STATUS_LABELS[order.status]?.class}`}>
                          {STATUS_LABELS[order.status]?.label}
                        </span>
                      </div>
                      <div className="flex items-center gap-4 text-sm text-slate-500">
                        <span className="flex items-center">
                          <Calendar className="h-4 w-4 mr-1" />
                          {format(new Date(order.created_at), 'dd MMM yyyy', { locale: ru })}
                        </span>
                        <span className="flex items-center">
                          <Package className="h-4 w-4 mr-1" />
                          {order.items.length} поз.
                        </span>
                      </div>
                    </div>
                    <div className="text-right flex items-start gap-2">
                      <div>
                        <div className="text-lg font-semibold font-mono text-blue-600">
                          {order.total_price.toLocaleString()} ₽
                        </div>
                        <ChevronRight className={`h-5 w-5 text-slate-400 ml-auto transition-transform ${
                          selectedOrder?.id === order.id ? 'rotate-90' : ''
                        }`} />
                      </div>
                    </div>
                  </div>

                  {/* Expanded details */}
                  {selectedOrder?.id === order.id && (
                    <div className="mt-6 pt-6 border-t border-slate-200 animate-fade-in">
                      <h4 className="font-medium text-slate-900 mb-3">Позиции заказа</h4>
                      <div className="space-y-2">
                        {order.items.map((item, idx) => (
                          <div key={idx} className="flex justify-between items-center py-2 px-3 bg-slate-50 rounded-md text-sm">
                            <div className="flex items-center gap-4">
                              <span className="font-mono text-slate-600">{idx + 1}.</span>
                              <span className="font-mono">{item.width}×{item.height} мм</span>
                              <span className="text-slate-500">× {item.quantity}</span>
                              <span className="text-slate-500">{item.installation_type}</span>
                            </div>
                            <span className="font-mono">{item.item_price?.toLocaleString()} ₽</span>
                          </div>
                        ))}
                      </div>
                      
                      <div className="mt-4 grid grid-cols-2 gap-4 text-sm">
                        <div className="flex items-center text-slate-600">
                          <Calendar className="h-4 w-4 mr-2" />
                          Желаемая дата: {order.desired_date}
                        </div>
                        <div className="flex items-center text-slate-600">
                          <Phone className="h-4 w-4 mr-2" />
                          {order.contact_phone}
                        </div>
                      </div>
                      
                      {order.notes && (
                        <div className="mt-3 flex items-start text-sm text-slate-600">
                          <FileText className="h-4 w-4 mr-2 mt-0.5" />
                          {order.notes}
                        </div>
                      )}

                      {/* Actions for new orders */}
                      {order.status === 'new' && (
                        <div className="mt-4 pt-4 border-t border-slate-200 flex gap-3">
                          <Link to={`/?edit=${order.id}`} onClick={(e) => e.stopPropagation()}>
                            <Button variant="outline" size="sm" data-testid={`edit-order-${order.id.slice(0, 8)}`}>
                              <Edit className="h-4 w-4 mr-2" />
                              Редактировать
                            </Button>
                          </Link>
                          <Button 
                            variant="outline" 
                            size="sm" 
                            className="text-red-600 hover:text-red-700 hover:bg-red-50"
                            onClick={(e) => openCancelDialog(order, e)}
                            data-testid={`cancel-order-${order.id.slice(0, 8)}`}
                          >
                            <X className="h-4 w-4 mr-2" />
                            Отменить
                          </Button>
                        </div>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </main>

      {/* Cancel confirmation dialog */}
      <Dialog open={cancelDialogOpen} onOpenChange={setCancelDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Отменить заказ?</DialogTitle>
            <DialogDescription>
              Вы уверены, что хотите отменить заказ #{orderToCancel?.id?.slice(0, 8)}? 
              Это действие нельзя будет отменить.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button 
              variant="outline" 
              onClick={() => setCancelDialogOpen(false)}
              disabled={cancelling}
            >
              Нет, оставить
            </Button>
            <Button 
              variant="destructive" 
              onClick={handleCancelOrder}
              disabled={cancelling}
              data-testid="confirm-cancel-btn"
            >
              {cancelling ? 'Отмена...' : 'Да, отменить'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default OrdersPage;
