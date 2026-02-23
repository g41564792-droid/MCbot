import React, { useState, useEffect } from 'react';
import { useNavigate, Link, useSearchParams } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Checkbox } from '../components/ui/checkbox';
import { Textarea } from '../components/ui/textarea';
import { Calendar } from '../components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '../components/ui/popover';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { RadioGroup, RadioGroupItem } from '../components/ui/radio-group';
import { Separator } from '../components/ui/separator';
import { format, addDays, parseISO } from 'date-fns';
import { ru } from 'date-fns/locale';
import { QRCodeSVG } from 'qrcode.react';
import { 
  Ruler, Plus, Minus, Trash2, CalendarIcon, Send, AlertCircle, 
  LogIn, User, ShoppingCart, ChevronRight, Info, MessageCircle, Save
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const TELEGRAM_BOT_URL = 'https://t.me/OlWait_MC_Bot';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Installation types
const INSTALLATION_TYPES = [
  { id: 'проемная_наружный', label: 'Проемная (наружный)', group: 'Проемная' },
  { id: 'проемная_внутренний', label: 'Проемная (внутренний)', group: 'Проемная' },
  { id: 'проемная_встраиваемый', label: 'Проемная (встраиваемый)', group: 'Проемная' },
  { id: 'дверная', label: 'Дверная', group: 'Дверная' },
  { id: 'роллетная', label: 'Роллетная', group: 'Роллетная' },
];

// Colors by installation type
const getColors = (installationType) => {
  if (installationType === 'дверная' || installationType === 'роллетная') {
    return [
      { id: 'белый', label: 'Белый' },
      { id: 'коричневый', label: 'Коричневый' },
    ];
  }
  return [
    { id: 'белый', label: 'Белый' },
    { id: 'коричневый', label: 'Коричневый' },
    { id: 'антрацит', label: 'Антрацит' },
    { id: 'ral', label: 'Иной цвет по RAL' },
  ];
};

// Mounting types
const MOUNTING_TYPES = [
  { id: 'z_bracket', label: 'Z-образные кронштейны' },
  { id: 'metal_hooks', label: 'Металлические зацепы' },
  { id: 'plastic_hooks', label: 'Пластиковые зацепы' },
];

// Mesh types
const MESH_TYPES = [
  { id: 'стандартное', label: 'Стандартное' },
  { id: 'антипыль', label: 'Антипыль' },
  { id: 'антимошка', label: 'Антимошка' },
  { id: 'антикошка', label: 'Антикошка' },
];

const defaultItem = () => ({
  id: Date.now(),
  installation_type: 'проемная_наружный',
  width: '',
  height: '',
  quantity: 1,
  color: 'белый',
  ral_color_description: '',
  mounting_type: 'z_bracket',
  mounting_by_manufacturer: true,
  mesh_type: 'стандартное',
  impost: false,
  impost_orientation: 'вертикально',
  notes: '',
});

const OrderFormPage = () => {
  const navigate = useNavigate();
  const { user, isAdmin } = useAuth();
  const [items, setItems] = useState([defaultItem()]);
  const [desiredDate, setDesiredDate] = useState(addDays(new Date(), 1));
  const [orderNotes, setOrderNotes] = useState('');
  const [contactPhone, setContactPhone] = useState(user?.phone || '');
  const [prices, setPrices] = useState({ items: [], total: 0 });
  const [loading, setLoading] = useState(false);
  const [calendarOpen, setCalendarOpen] = useState(false);

  // Calculate prices
  useEffect(() => {
    const calculatePrices = async () => {
      const validItems = items.filter(i => i.width >= 150 && i.height >= 150);
      if (validItems.length === 0) {
        setPrices({ items: [], total: 0 });
        return;
      }
      
      try {
        const payload = validItems.map(i => ({
          installation_type: i.installation_type,
          width: parseInt(i.width),
          height: parseInt(i.height),
          quantity: i.quantity,
          color: i.color === 'ral' ? `ral_${i.ral_color_description}` : i.color,
          mounting_type: i.mounting_type,
          mounting_by_manufacturer: i.mounting_by_manufacturer,
          mesh_type: i.mesh_type,
          impost: i.impost,
          impost_orientation: i.impost ? i.impost_orientation : null,
        }));
        
        const res = await axios.post(`${API}/calculate-price`, payload);
        setPrices(res.data);
      } catch (err) {
        console.error('Price calculation error:', err);
      }
    };
    
    const debounce = setTimeout(calculatePrices, 500);
    return () => clearTimeout(debounce);
  }, [items]);

  const updateItem = (index, field, value) => {
    setItems(prev => {
      const newItems = [...prev];
      newItems[index] = { ...newItems[index], [field]: value };
      return newItems;
    });
  };

  const addItem = () => {
    const lastItem = items[items.length - 1];
    setItems(prev => [...prev, {
      ...defaultItem(),
      id: Date.now(),
      installation_type: lastItem.installation_type,
      color: lastItem.color,
      ral_color_description: lastItem.ral_color_description,
      mounting_type: lastItem.mounting_type,
      mounting_by_manufacturer: lastItem.mounting_by_manufacturer,
      mesh_type: lastItem.mesh_type,
    }]);
  };

  const removeItem = (index) => {
    if (items.length > 1) {
      setItems(prev => prev.filter((_, i) => i !== index));
    }
  };

  const validateItems = () => {
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (!item.width || !item.height) {
        toast.error(`Позиция ${i + 1}: укажите ширину и высоту`);
        return false;
      }
      const w = parseInt(item.width);
      const h = parseInt(item.height);
      if (w < 150 || w > 3000 || h < 150 || h > 3000) {
        toast.error(`Позиция ${i + 1}: размеры должны быть от 150 до 3000 мм`);
        return false;
      }
      if (item.quantity > 30) {
        toast.error(`Позиция ${i + 1}: для заказа более 30 единиц свяжитесь с нами по телефону`);
        return false;
      }
      if (item.color === 'ral' && !item.ral_color_description) {
        toast.error(`Позиция ${i + 1}: укажите код RAL`);
        return false;
      }
    }
    return true;
  };

  const handleSubmit = async () => {
    if (!user) {
      toast.error('Для оформления заказа необходимо авторизоваться');
      navigate('/auth');
      return;
    }

    if (!validateItems()) return;

    setLoading(true);
    try {
      const payload = {
        items: items.map(i => ({
          installation_type: i.installation_type,
          width: parseInt(i.width),
          height: parseInt(i.height),
          quantity: i.quantity,
          color: i.color === 'ral' ? `ral_${i.ral_color_description}` : i.color,
          ral_color_description: i.color === 'ral' ? i.ral_color_description : null,
          mounting_type: i.mounting_type,
          mounting_by_manufacturer: i.mounting_by_manufacturer,
          mesh_type: i.mesh_type,
          impost: i.impost,
          impost_orientation: i.impost ? i.impost_orientation : null,
          notes: i.notes,
        })),
        desired_date: format(desiredDate, 'yyyy-MM-dd'),
        notes: orderNotes,
        contact_phone: contactPhone || user.phone,
      };

      await axios.post(`${API}/orders`, payload);
      toast.success('Заказ успешно оформлен!');
      navigate('/orders');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Ошибка при создании заказа');
    } finally {
      setLoading(false);
    }
  };

  const showImpostRecommendation = (item) => {
    return (parseInt(item.width) > 1200 || parseInt(item.height) > 1200) && !item.impost;
  };

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-slate-900 tracking-tight">Москитные сетки</h1>
            <p className="text-sm text-slate-500">Оформление заказа</p>
          </div>
          <div className="flex items-center gap-3">
            {user ? (
              <>
                <Link to="/orders">
                  <Button variant="outline" size="sm" data-testid="my-orders-btn">
                    <ShoppingCart className="h-4 w-4 mr-2" />
                    Мои заказы
                  </Button>
                </Link>
                {isAdmin && (
                  <Link to="/admin">
                    <Button variant="outline" size="sm" data-testid="admin-btn">
                      Админ
                    </Button>
                  </Link>
                )}
                <span className="text-sm text-slate-600">{user.name}</span>
              </>
            ) : (
              <Link to="/auth">
                <Button variant="outline" size="sm" data-testid="login-btn">
                  <LogIn className="h-4 w-4 mr-2" />
                  Войти
                </Button>
              </Link>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Order Items */}
          <div className="lg:col-span-2 space-y-6">
            {items.map((item, index) => (
              <Card key={item.id} className="border-slate-200 shadow-sm animate-fade-in">
                <CardHeader className="pb-4">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-lg">Позиция {index + 1}</CardTitle>
                    {items.length > 1 && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => removeItem(index)}
                        data-testid={`remove-item-${index}`}
                        className="text-red-600 hover:text-red-700 hover:bg-red-50"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                </CardHeader>
                <CardContent className="space-y-6">
                  {/* Row 1: Installation Type */}
                  <div>
                    <Label className="text-sm font-medium mb-3 block">Тип установки</Label>
                    <Select
                      value={item.installation_type}
                      onValueChange={(v) => updateItem(index, 'installation_type', v)}
                    >
                      <SelectTrigger className="h-12 bg-slate-50" data-testid={`installation-type-${index}`}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {INSTALLATION_TYPES.map((type) => (
                          <SelectItem key={type.id} value={type.id}>
                            {type.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  {/* Row 2: Dimensions */}
                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <Label className="text-sm font-medium mb-2 block">Ширина, мм *</Label>
                      <div className="relative">
                        <Ruler className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                        <Input
                          type="number"
                          placeholder="800"
                          value={item.width}
                          onChange={(e) => updateItem(index, 'width', e.target.value)}
                          className="pl-10 h-12 bg-slate-50 font-mono"
                          data-testid={`width-${index}`}
                          min="150"
                          max="3000"
                        />
                      </div>
                      {item.width && (parseInt(item.width) < 150 || parseInt(item.width) > 3000) && (
                        <p className="text-xs text-red-600 mt-1 flex items-center">
                          <AlertCircle className="h-3 w-3 mr-1" />
                          От 150 до 3000 мм
                        </p>
                      )}
                    </div>
                    <div>
                      <Label className="text-sm font-medium mb-2 block">Высота, мм *</Label>
                      <div className="relative">
                        <Ruler className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400 rotate-90" />
                        <Input
                          type="number"
                          placeholder="1200"
                          value={item.height}
                          onChange={(e) => updateItem(index, 'height', e.target.value)}
                          className="pl-10 h-12 bg-slate-50 font-mono"
                          data-testid={`height-${index}`}
                          min="150"
                          max="3000"
                        />
                      </div>
                      {item.height && (parseInt(item.height) < 150 || parseInt(item.height) > 3000) && (
                        <p className="text-xs text-red-600 mt-1 flex items-center">
                          <AlertCircle className="h-3 w-3 mr-1" />
                          От 150 до 3000 мм
                        </p>
                      )}
                    </div>
                    <div>
                      <Label className="text-sm font-medium mb-2 block">Количество</Label>
                      <div className="flex items-center gap-2">
                        <Button
                          type="button"
                          variant="outline"
                          size="icon"
                          className="h-12 w-12"
                          onClick={() => updateItem(index, 'quantity', Math.max(1, item.quantity - 1))}
                          data-testid={`qty-minus-${index}`}
                        >
                          <Minus className="h-4 w-4" />
                        </Button>
                        <Input
                          type="number"
                          value={item.quantity}
                          onChange={(e) => updateItem(index, 'quantity', Math.max(1, Math.min(30, parseInt(e.target.value) || 1)))}
                          className="h-12 text-center font-mono bg-slate-50"
                          data-testid={`quantity-${index}`}
                          min="1"
                          max="30"
                        />
                        <Button
                          type="button"
                          variant="outline"
                          size="icon"
                          className="h-12 w-12"
                          onClick={() => updateItem(index, 'quantity', Math.min(30, item.quantity + 1))}
                          data-testid={`qty-plus-${index}`}
                        >
                          <Plus className="h-4 w-4" />
                        </Button>
                      </div>
                      {item.quantity >= 30 && (
                        <p className="text-xs text-amber-600 mt-1">
                          Для большего количества свяжитесь с нами
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Impost recommendation */}
                  {showImpostRecommendation(item) && (
                    <div className="bg-amber-50 border border-amber-200 rounded-md p-3 flex items-start gap-2">
                      <Info className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
                      <p className="text-sm text-amber-800">
                        Рекомендуется постановка импоста для изделий с размером более 1200 мм
                      </p>
                    </div>
                  )}

                  {/* Impost checkbox */}
                  <div className="flex items-center gap-4">
                    <div className="flex items-center space-x-2">
                      <Checkbox
                        id={`impost-${index}`}
                        checked={item.impost}
                        onCheckedChange={(checked) => updateItem(index, 'impost', checked)}
                        data-testid={`impost-${index}`}
                      />
                      <Label htmlFor={`impost-${index}`} className="text-sm cursor-pointer">
                        Импост
                      </Label>
                    </div>
                    {item.impost && (
                      <RadioGroup
                        value={item.impost_orientation}
                        onValueChange={(v) => updateItem(index, 'impost_orientation', v)}
                        className="flex gap-4"
                      >
                        <div className="flex items-center space-x-2">
                          <RadioGroupItem value="вертикально" id={`impost-v-${index}`} />
                          <Label htmlFor={`impost-v-${index}`} className="text-sm cursor-pointer">Вертикально</Label>
                        </div>
                        <div className="flex items-center space-x-2">
                          <RadioGroupItem value="горизонтально" id={`impost-h-${index}`} />
                          <Label htmlFor={`impost-h-${index}`} className="text-sm cursor-pointer">Горизонтально</Label>
                        </div>
                      </RadioGroup>
                    )}
                  </div>

                  <Separator />

                  {/* Row 3: Color, Mounting, Mesh */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <Label className="text-sm font-medium mb-2 block">Цвет</Label>
                      <Select
                        value={item.color}
                        onValueChange={(v) => updateItem(index, 'color', v)}
                      >
                        <SelectTrigger className="h-12 bg-slate-50" data-testid={`color-${index}`}>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {getColors(item.installation_type).map((color) => (
                            <SelectItem key={color.id} value={color.id}>
                              {color.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      {item.color === 'ral' && (
                        <Input
                          placeholder="Код RAL, например: 7016"
                          value={item.ral_color_description}
                          onChange={(e) => updateItem(index, 'ral_color_description', e.target.value)}
                          className="mt-2 h-12 bg-slate-50"
                          data-testid={`ral-code-${index}`}
                        />
                      )}
                    </div>
                    <div>
                      <Label className="text-sm font-medium mb-2 block">Крепление</Label>
                      <Select
                        value={item.mounting_type}
                        onValueChange={(v) => updateItem(index, 'mounting_type', v)}
                      >
                        <SelectTrigger className="h-12 bg-slate-50" data-testid={`mounting-${index}`}>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {MOUNTING_TYPES.map((mount) => (
                            <SelectItem key={mount.id} value={mount.id}>
                              {mount.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <div className="flex items-center space-x-2 mt-2">
                        <Checkbox
                          id={`mounting-mfg-${index}`}
                          checked={item.mounting_by_manufacturer}
                          onCheckedChange={(checked) => updateItem(index, 'mounting_by_manufacturer', checked)}
                          data-testid={`mounting-mfg-${index}`}
                        />
                        <Label htmlFor={`mounting-mfg-${index}`} className="text-xs cursor-pointer text-slate-600">
                          Прикручивает изготовитель
                        </Label>
                      </div>
                    </div>
                    <div>
                      <Label className="text-sm font-medium mb-2 block">Тип полотна</Label>
                      <Select
                        value={item.mesh_type}
                        onValueChange={(v) => updateItem(index, 'mesh_type', v)}
                      >
                        <SelectTrigger className="h-12 bg-slate-50" data-testid={`mesh-${index}`}>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {MESH_TYPES.map((mesh) => (
                            <SelectItem key={mesh.id} value={mesh.id}>
                              {mesh.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  {/* Item notes */}
                  <div>
                    <Label className="text-sm font-medium mb-2 block">Примечание к позиции</Label>
                    <Textarea
                      placeholder="Дополнительные сведения..."
                      value={item.notes}
                      onChange={(e) => updateItem(index, 'notes', e.target.value)}
                      className="bg-slate-50 resize-none"
                      rows={2}
                      data-testid={`item-notes-${index}`}
                    />
                  </div>
                </CardContent>
              </Card>
            ))}

            {/* Add item button */}
            <Button
              type="button"
              variant="outline"
              onClick={addItem}
              className="w-full h-12 border-dashed"
              data-testid="add-item-btn"
            >
              <Plus className="h-4 w-4 mr-2" />
              Добавить позицию
            </Button>
          </div>

          {/* Sidebar - Summary */}
          <div className="lg:col-span-1">
            <div className="sticky top-24 space-y-4">
              <Card className="border-slate-200 shadow-sm">
                <CardHeader>
                  <CardTitle className="text-lg">Итого</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {prices.items.map((p, i) => (
                    <div key={i} className="flex justify-between text-sm">
                      <span className="text-slate-600">
                        {p.width}×{p.height} мм × {p.quantity} шт
                      </span>
                      <span className="font-mono">{p.price.toLocaleString()} ₽</span>
                    </div>
                  ))}
                  <Separator />
                  <div className="flex justify-between text-lg font-semibold">
                    <span>Сумма:</span>
                    <span className="font-mono text-blue-600" data-testid="total-price">
                      {prices.total.toLocaleString()} ₽
                    </span>
                  </div>
                </CardContent>
              </Card>

              <Card className="border-slate-200 shadow-sm">
                <CardHeader>
                  <CardTitle className="text-lg">Дата готовности</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <Popover open={calendarOpen} onOpenChange={setCalendarOpen}>
                    <PopoverTrigger asChild>
                      <Button
                        variant="outline"
                        className="w-full h-12 justify-start text-left font-normal bg-slate-50"
                        data-testid="date-picker"
                      >
                        <CalendarIcon className="mr-2 h-4 w-4" />
                        {format(desiredDate, 'dd MMMM yyyy', { locale: ru })}
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-auto p-0" align="start">
                      <Calendar
                        mode="single"
                        selected={desiredDate}
                        onSelect={(date) => {
                          if (date) {
                            setDesiredDate(date);
                            setCalendarOpen(false);
                          }
                        }}
                        disabled={(date) => date < addDays(new Date(), 1)}
                        initialFocus
                      />
                    </PopoverContent>
                  </Popover>

                  <div>
                    <Label className="text-sm font-medium mb-2 block">Контактный телефон</Label>
                    <Input
                      placeholder="+7 (999) 123-45-67"
                      value={contactPhone}
                      onChange={(e) => setContactPhone(e.target.value)}
                      className="h-12 bg-slate-50"
                      data-testid="contact-phone"
                    />
                  </div>

                  <div>
                    <Label className="text-sm font-medium mb-2 block">Примечание к заказу</Label>
                    <Textarea
                      placeholder="Дополнительные сведения..."
                      value={orderNotes}
                      onChange={(e) => setOrderNotes(e.target.value)}
                      className="bg-slate-50 resize-none"
                      rows={3}
                      data-testid="order-notes"
                    />
                  </div>

                  <Button
                    onClick={handleSubmit}
                    disabled={loading || prices.total === 0}
                    className="w-full h-12 bg-blue-600 hover:bg-blue-700"
                    data-testid="submit-order-btn"
                  >
                    {loading ? (
                      <span className="animate-pulse">Оформление...</span>
                    ) : (
                      <>
                        <Send className="h-4 w-4 mr-2" />
                        Отправить заказ
                      </>
                    )}
                  </Button>
                </CardContent>
              </Card>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};

export default OrderFormPage;
