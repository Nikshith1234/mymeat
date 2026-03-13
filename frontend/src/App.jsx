import React, { useState, useEffect, useCallback } from 'react';
import { Clock, CheckCircle2, ShoppingBag, MapPin, Phone, ChefHat, Play, Trash2, UtensilsCrossed, LogOut, Link as LinkIcon, X, Send } from 'lucide-react';
import Login from './Login';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';


const TABS = [
  { key: 'pending', label: 'Pending', color: 'orange' },
  { key: 'awaiting_payment', label: 'Awaiting Payment', color: 'yellow' },
  { key: 'paid', label: 'Paid', color: 'purple' },
  { key: 'preparing', label: 'Started Prep', color: 'blue' },
  { key: 'ready', label: 'Ready', color: 'emerald' },
];

const tabStyles = {
  orange: { active: 'border-orange-500 text-orange-600', badge: 'bg-orange-500', num: 'text-orange-500' },
  yellow: { active: 'border-amber-500 text-amber-600', badge: 'bg-amber-500', num: 'text-amber-500' },
  purple: { active: 'border-purple-500 text-purple-600', badge: 'bg-purple-500', num: 'text-purple-500' },
  blue: { active: 'border-blue-500 text-blue-600', badge: 'bg-blue-500', num: 'text-blue-500' },
  emerald: { active: 'border-emerald-500 text-emerald-600', badge: 'bg-emerald-500', num: 'text-emerald-500' },
};

const cardBorder = { 
  pending: 'border-orange-300', 
  awaiting_payment: 'border-amber-300',
  paid: 'border-purple-300',
  preparing: 'border-blue-300', 
  ready: 'border-emerald-300' 
};
const statusBadge = {
  pending: 'bg-orange-100 text-orange-700 border-orange-200',
  awaiting_payment: 'bg-amber-100 text-amber-700 border-amber-200',
  paid: 'bg-purple-100 text-purple-700 border-purple-200',
  preparing: 'bg-blue-100 text-blue-700 border-blue-200',
  ready: 'bg-emerald-100 text-emerald-700 border-emerald-200',
};

export default function App() {
  const [token, setToken] = useState(localStorage.getItem('admin_token'));
  const [orders, setOrders] = useState([]);
  const [activeTab, setActiveTab] = useState('pending');
  const [loading, setLoading] = useState({});
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [paymentLink, setPaymentLink] = useState('');
  const [processingOrderId, setProcessingOrderId] = useState(null);
  const [sendingLink, setSendingLink] = useState(false);

  const handleLogin = (newToken) => {
    localStorage.setItem('admin_token', newToken);
    setToken(newToken);
  };

  const handleLogout = () => {
    localStorage.removeItem('admin_token');
    setToken(null);
  };

  const fetchOrders = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetch(`${API}/api/orders`, {
        headers: { 
          'ngrok-skip-browser-warning': 'true',
          'Authorization': `Bearer ${token}`
        }
      });
      if (res.status === 401) { handleLogout(); return; }
      if (res.ok) setOrders(await res.json());
    } catch (e) { console.error('Fetch error:', e); }
  }, [token]);

  useEffect(() => {
    fetchOrders();
    const id = setInterval(fetchOrders, 5000);
    return () => clearInterval(id);
  }, [fetchOrders]);

  const updateStatus = async (orderId, newStatus) => {


    setLoading(l => ({ ...l, [orderId]: true }));
    setOrders(prev => prev.map(o => o.order_id === orderId ? { ...o, status: newStatus } : o));

    try {
      const res = await fetch(`${API}/api/orders/${orderId}/status`, {
        method: 'PATCH',
        headers: { 
          'Content-Type': 'application/json',
          'ngrok-skip-browser-warning': 'true',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ status: newStatus }),
      });
      if (res.status === 401) handleLogout();
    } catch { /* ignore */ }
    setLoading(l => ({ ...l, [orderId]: false }));
  };

  const processOrder = async (orderId) => {
    // Moves to awaiting_payment and generates razorpay link natively backend


    setLoading(l => ({ ...l, [orderId]: true }));
    setOrders(prev => prev.map(o => o.order_id === orderId ? { ...o, status: 'awaiting_payment' } : o));

    try {
      const res = await fetch(`${API}/api/orders/${orderId}/process`, {
        method: 'POST',
        headers: { 
          'ngrok-skip-browser-warning': 'true',
          'Authorization': `Bearer ${token}`
        }
      });
      if (res.status === 401) { handleLogout(); return; }
      
      const data = await res.json();
      if (data.payment_link_url) {
        // Automatically send the WhatsApp link since the modal is removed.
        await fetch(`${API}/api/orders/${orderId}/send_payment_link`, {
          method: 'POST',
          headers: {
            'ngrok-skip-browser-warning': 'true',
            'Authorization': `Bearer ${token}`
          }
        });
      }
      // On success, backend updates to PREPARING
    } catch { /* ignore */ }
    setLoading(l => ({ ...l, [orderId]: false }));
  };

  const sendPaymentLink = async () => {
    if (!processingOrderId) return;
    setSendingLink(true);
    try {
      const res = await fetch(`${API}/api/orders/${processingOrderId}/send_payment_link`, {
        method: 'POST',
        headers: {
          'ngrok-skip-browser-warning': 'true',
          'Authorization': `Bearer ${token}`
        }
      });
      if (res.status === 401) handleLogout();
      if (res.ok) {
        setIsModalOpen(false);
        setPaymentLink('');
        setProcessingOrderId(null);
      } else {
        alert('Failed to send link via WhatsApp.');
      }
    } catch (e) { console.error('Error sending link:', e); }
    setSendingLink(false);
  };

  const clearOrder = async (orderId) => {


    setLoading(l => ({ ...l, [orderId]: true }));
    setOrders(prev => prev.filter(o => o.order_id !== orderId));

    try {
      const res = await fetch(`${API}/api/orders/${orderId}`, { 
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (res.status === 401) handleLogout();
    } catch { /* ignore */ }
  };

  const countOf = (s) => orders.filter(o => o.status === s).length;
  const visible = orders.filter(o => o.status === activeTab);

  if (!token) {
    return <Login onLogin={handleLogin} />;
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800" style={{ fontFamily: "'Inter', system-ui, sans-serif" }}>

      {/* ── Header ── */}
      <header className="bg-white border-b border-slate-200 px-6 py-4 sticky top-0 z-10 shadow-sm">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div className="flex flex-1 items-center gap-3">
            <span className="bg-rose-600 text-white p-2 rounded-xl shadow">
              <ChefHat className="w-6 h-6" />
            </span>
            <div>
              <h1 className="text-xl font-extrabold text-slate-900 tracking-tight leading-none">Meatcraft Dashboard</h1>
              <p className="text-xs text-slate-500 flex items-center gap-1.5 mt-1 font-medium">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </span>
                Live · Auto-refreshing every 5 s
              </p>
            </div>
          </div>

          <div className="flex gap-3 items-center">
            {TABS.map(t => (
              <div key={t.key} className="flex flex-col items-center bg-slate-50 border border-slate-200 rounded-xl px-4 py-2 min-w-[72px]">
                <span className={`text-2xl font-extrabold ${tabStyles[t.color].num}`}>{countOf(t.key)}</span>
                <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wide">{t.label}</span>
              </div>
            ))}
            
            {/* Logout Button */}
            <div className="ml-4 pl-4 border-l border-slate-200">
               <button onClick={handleLogout} className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors" title="Log out">
                  <LogOut className="w-5 h-5" />
               </button>
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-6 mt-6">

        {/* ── Tabs ── */}
        <div className="flex border-b border-slate-200">
          {TABS.map(t => {
            const active = activeTab === t.key;
            const s = tabStyles[t.color];
            const n = countOf(t.key);
            return (
              <button
                key={t.key}
                onClick={() => setActiveTab(t.key)}
                className={`px-6 py-3 text-sm font-bold border-b-2 -mb-px transition-colors
                  ${active ? s.active + ' bg-white' : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'}`}
              >
                {t.label}
                {n > 0 && (
                  <span className={`ml-2 ${s.badge} text-white text-[10px] font-bold rounded-full px-1.5 py-0.5 align-middle`}>
                    {n}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* ── Grid ── */}
        <div className="py-6">
          {visible.length === 0 ? (
            <div className="text-center py-20 bg-white rounded-2xl border border-slate-200">
              <UtensilsCrossed className="w-14 h-14 mx-auto mb-4 text-slate-300" />
              <p className="text-lg font-bold text-slate-500">No {TABS.find(t => t.key === activeTab)?.label} orders</p>
              <p className="text-sm text-slate-400 mt-1 font-medium">Orders will appear here automatically.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
              {visible.map(order => (
                <OrderCard
                  key={order.order_id}
                  order={order}
                  loading={!!loading[order.order_id]}
                  onUpdateStatus={updateStatus}
                  onProcess={processOrder}
                  onClear={clearOrder}
                />
              ))}
            </div>
          )}
        </div>
      </div>


    </div>
  );
}

function OrderCard({ order, loading, onUpdateStatus, onProcess, onClear }) {
  return (
    <div className={`bg-white rounded-2xl border-2 ${cardBorder[order.status] || 'border-slate-200'} shadow-sm flex flex-col overflow-hidden hover:shadow-md transition-shadow`}>

      {/* Top */}
      <div className="px-5 pt-4 pb-3 flex items-start justify-between border-b border-slate-100">
        <div>
          <span className="font-extrabold text-slate-900 text-lg">{order.order_id}</span>
          <p className="text-xs text-slate-400 flex items-center gap-1 mt-0.5 font-medium">
            <Clock className="w-3 h-3" /> {order.timestamp}
          </p>
        </div>
        <span className={`text-[10px] font-extrabold uppercase tracking-widest px-2.5 py-1 rounded-full border ${statusBadge[order.status] || ''}`}>
          {order.status}
        </span>
      </div>

      {/* Order type + payment */}
      <div className="px-5 py-3 flex items-center justify-between border-b border-slate-100 bg-slate-50/60 text-sm">
        <span className={`flex items-center gap-1.5 font-bold ${order.order_type === 'DELIVERY' ? 'text-indigo-600' : 'text-orange-600'}`}>
          <ShoppingBag className="w-4 h-4" /> {order.order_type}
        </span>
        <div className="flex items-center gap-2">
          {order.payment_status === 'PAID' && <span className="text-emerald-600"><CheckCircle2 className="w-4 h-4" /></span>}
          <span className={`font-bold px-2 py-0.5 rounded text-xs ${order.payment_status === 'PAID' ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'}`}>
            {order.payment_status}
          </span>
        </div>
      </div>

      {/* Customer */}
      <div className="px-5 py-3 border-b border-slate-100 space-y-2">
        <div className="flex items-center justify-between">
          <div>
            <p className="font-bold text-slate-800">{order.customer_name}</p>
            <p className="text-xs text-slate-500 font-medium mt-0.5 flex items-center gap-1">
              <Phone className="w-3 h-3" /> {order.customer_phone}
            </p>
          </div>
          <a href={`tel:${order.customer_phone}`}
            className="flex items-center gap-1 text-xs font-bold text-indigo-600 border border-indigo-200 bg-indigo-50 px-2.5 py-1.5 rounded-lg hover:bg-indigo-100 transition-colors">
            <Phone className="w-3.5 h-3.5" /> Call
          </a>
        </div>
        {order.order_type === 'DELIVERY' && order.address && (
          <p className="text-xs text-slate-500 flex items-start gap-1.5 font-medium">
            <MapPin className="w-3.5 h-3.5 shrink-0 mt-0.5 text-slate-400" />
            <span className="leading-snug">{order.address}</span>
          </p>
        )}
        {order.order_type === 'PICKUP' && order.arrival_time && (
          <p className="text-xs text-amber-600 flex items-start gap-1.5 font-bold bg-amber-50 p-2 rounded-lg border border-amber-100 mt-2">
            <Clock className="w-4 h-4 shrink-0 mt-0.5" />
            <span className="leading-snug">Pickup Time: {order.arrival_time}</span>
          </p>
        )}
      </div>

      {/* Items */}
      <div className="px-5 py-4 flex-1">
        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-3">Items ({order.items?.length || 0})</p>
        <ul className="space-y-3">
          {order.items?.map((item, i) => (
            <li key={i} className="flex justify-between items-start text-sm">
              <div className="flex gap-3">
                <span className="font-extrabold text-rose-500 min-w-[1.5rem]">{item.quantity}×</span>
                <div>
                  <p className="font-bold text-slate-800">{item.item_name}</p>
                  {item.variation && <p className="text-slate-500 font-medium text-xs mt-0.5">{item.variation}</p>}
                </div>
              </div>
              <span className="font-bold text-slate-700">₹{item.final_price}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* Footer */}
      <div className="px-5 py-4 bg-slate-50 border-t border-slate-100 flex items-center justify-between mt-auto">
        <span className="text-xl font-extrabold text-slate-900">₹{order.total_amount?.toFixed(2)}</span>
        <div className="flex gap-2">
          {order.status === 'pending' && (
            <button disabled={loading} onClick={() => onProcess(order.order_id)}
              className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-lg transition-colors active:scale-95 shadow-sm disabled:opacity-60">
              <LinkIcon className="w-3.5 h-3.5 text-white" /> Process Order
            </button>
          )}
          {order.status === 'awaiting_payment' && (
            <button disabled={loading} onClick={() => alert("Payment link already sent via WP. Await Razorpay Webhook to move this to Paid.")}
              className="flex items-center gap-1.5 px-4 py-2 bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100 text-xs font-bold rounded-lg transition-colors active:scale-95 shadow-sm disabled:opacity-60">
              <Clock className="w-3.5 h-3.5" /> Awaiting Payment
            </button>
          )}
          {order.status === 'paid' && (
            <button disabled={loading} onClick={() => onUpdateStatus(order.order_id, 'preparing')}
              className="flex items-center gap-1.5 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white text-xs font-bold rounded-lg transition-colors active:scale-95 shadow-sm disabled:opacity-60">
              <ChefHat className="w-3.5 h-3.5 text-white" /> Start Prep
            </button>
          )}
          {order.status === 'preparing' && (
            <button disabled={loading} onClick={() => onUpdateStatus(order.order_id, 'ready')}
              className="flex items-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold rounded-lg transition-colors active:scale-95 shadow-sm disabled:opacity-60">
              <CheckCircle2 className="w-3.5 h-3.5" /> Mark Ready
            </button>
          )}
          {order.status === 'ready' && (
            <button disabled={loading} onClick={() => onClear(order.order_id)}
              className="flex items-center gap-1.5 px-4 py-2 bg-slate-200 hover:bg-red-100 hover:text-red-700 text-slate-700 text-xs font-bold rounded-lg transition-colors active:scale-95 disabled:opacity-60">
              <Trash2 className="w-3.5 h-3.5" /> Clear Order
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

