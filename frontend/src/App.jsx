import React, { useState, useEffect } from 'react';
import { Clock, CheckCircle2, ShoppingBag, MapPin, Phone, ChefHat, Play } from 'lucide-react';

export default function App() {
    const [orders, setOrders] = useState([]);

    // Poll the backend every 5 seconds for new orders
    useEffect(() => {
        const fetchOrders = async () => {
            try {
                const response = await fetch('http://localhost:8000/api/orders');
                if (response.ok) {
                    const data = await response.json();
                    setOrders(data);
                }
            } catch (error) {
                console.error("Failed to fetch orders:", error);
            }
        };

        // Fetch immediately on load
        fetchOrders();

        // Then fetch every 5 seconds
        const intervalId = setInterval(fetchOrders, 5000);

        // Cleanup interval on unmount
        return () => clearInterval(intervalId);
    }, []);

    const updateOrderStatus = (orderId, newStatus) => {
        // Optimistically update the UI. 
        // Note: For a true production app, you would also send a POST/PUT request 
        // back to the backend here to permanently save this status change.
        setOrders(orders.map(o => o.order_id === orderId ? { ...o, status: newStatus } : o));
    };

    const getStatusStyles = (status) => {
        switch (status) {
            case 'pending': return 'text-orange-700 bg-orange-100 border-orange-200';
            case 'preparing': return 'text-blue-700 bg-blue-100 border-blue-200';
            case 'ready': return 'text-emerald-700 bg-emerald-100 border-emerald-200';
            default: return 'text-slate-600 bg-slate-100 border-slate-200';
        }
    };

    return (
        <div className="min-h-screen bg-slate-50 p-4 md:p-8 font-[Inter] text-slate-800">
            <div className="max-w-7xl mx-auto space-y-6">

                {/* Header */}
                <header className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-slate-200">
                    <div>
                        <h1 className="text-3xl font-bold tracking-tight text-slate-900 flex items-center gap-3">
                            <ChefHat className="text-rose-600 w-8 h-8" />
                            Meatcraft Live Orders
                        </h1>
                        <p className="text-slate-500 mt-1 flex items-center gap-2 font-medium">
                            <span className="relative flex h-2.5 w-2.5">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
                            </span>
                            System Online • Syncing with POS
                        </p>
                    </div>
                    <div className="flex gap-3">
                        <div className="card-base px-5 py-3 flex flex-col items-center min-w-[100px]">
                            <span className="text-3xl font-bold text-slate-800">{orders.length}</span>
                            <span className="text-xs text-slate-500 font-semibold uppercase tracking-wide">Total</span>
                        </div>
                        <div className="card-base px-5 py-3 flex flex-col items-center bg-rose-50 border-rose-100 min-w-[100px]">
                            <span className="text-3xl font-bold text-rose-600">{orders.filter(o => o.status === 'pending').length}</span>
                            <span className="text-xs text-rose-500 font-semibold uppercase tracking-wide">Pending</span>
                        </div>
                    </div>
                </header>

                {/* Orders Grid */}
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                    {orders.map((order) => (
                        <div key={order.order_id} className="card-base overflow-hidden flex flex-col hover:shadow-md transition-shadow">

                            {/* Card Header */}
                            <div className="p-5 border-b border-slate-100 bg-white">
                                <div className="flex justify-between items-start mb-3">
                                    <div>
                                        <h3 className="text-lg font-bold text-slate-900">{order.order_id}</h3>
                                        <p className="text-sm font-medium text-slate-500 flex items-center gap-1.5 mt-0.5">
                                            <Clock className="w-4 h-4 text-slate-400" /> {order.timestamp}
                                        </p>
                                    </div>
                                    <span className={`px-3 py-1 rounded-full text-xs font-bold border uppercase tracking-wider ${getStatusStyles(order.status)}`}>
                                        {order.status}
                                    </span>
                                </div>

                                <div className="flex items-center justify-between text-sm mt-4">
                                    <span className={`flex items-center gap-1.5 font-bold ${order.order_type === 'DELIVERY' ? 'text-indigo-600' : 'text-orange-600'}`}>
                                        <ShoppingBag className="w-4 h-4" /> {order.order_type}
                                    </span>
                                    <span className={`font-bold px-2 py-1 rounded text-xs ${order.payment_status === 'PAID' ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'}`}>
                                        {order.payment_status}
                                    </span>
                                </div>
                            </div>

                            {/* Customer Info */}
                            <div className="p-5 border-b border-slate-100 bg-slate-50/50 space-y-2.5">
                                <div className="flex items-center justify-between">
                                    <p className="font-bold text-slate-800">{order.customer_name}</p>
                                    <a href={`tel:${order.customer_phone}`} className="text-indigo-600 hover:text-indigo-700 hover:bg-indigo-50 font-semibold transition-colors flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-md border border-indigo-200 bg-white">
                                        <Phone className="w-3.5 h-3.5" /> Call
                                    </a>
                                </div>
                                {order.address && (
                                    <p className="text-sm text-slate-600 flex items-start gap-2 font-medium">
                                        <MapPin className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
                                        <span className="leading-snug">{order.address}</span>
                                    </p>
                                )}
                            </div>

                            {/* Order Items */}
                            <div className="p-5 flex-1 bg-white">
                                <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-4">Order Items ({order.items.length})</h4>
                                <ul className="space-y-4">
                                    {order.items.map((item, idx) => (
                                        <li key={idx} className="flex justify-between items-start">
                                            <div className="flex gap-4">
                                                <span className="font-bold text-rose-600 block min-w-[1.5rem] mt-0.5">{item.quantity}x</span>
                                                <div>
                                                    <p className="font-bold text-slate-800 text-sm">{item.item_name}</p>
                                                    {item.variation && <p className="text-sm text-slate-500 font-medium mt-0.5">{item.variation}</p>}
                                                </div>
                                            </div>
                                            <span className="text-sm font-bold text-slate-700">₹{item.final_price}</span>
                                        </li>
                                    ))}
                                </ul>
                            </div>

                            {/* Card Footer / Actions */}
                            <div className="p-5 bg-slate-50 border-t border-slate-200 flex items-center justify-between mt-auto">
                                <div className="text-xl font-bold text-slate-900">
                                    ₹{order.total_amount.toFixed(2)}
                                </div>
                                <div className="flex gap-2">
                                    {order.status === 'pending' && (
                                        <button
                                            onClick={() => updateOrderStatus(order.order_id, 'preparing')}
                                            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold rounded-lg transition-colors active:scale-95 flex items-center gap-1.5 shadow-sm"
                                        >
                                            <Play className="w-4 h-4 fill-current" /> Start Prep
                                        </button>
                                    )}
                                    {order.status === 'preparing' && (
                                        <button
                                            onClick={() => updateOrderStatus(order.order_id, 'ready')}
                                            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-bold rounded-lg transition-colors active:scale-95 flex items-center gap-1.5 shadow-sm"
                                        >
                                            <CheckCircle2 className="w-4 h-4" /> Mark Ready
                                        </button>
                                    )}
                                    {order.status === 'ready' && (
                                        <button
                                            onClick={async () => {
                                                try {
                                                    const res = await fetch(`http://localhost:8000/api/orders/${order.order_id}`, { method: 'DELETE' });
                                                    if (res.ok) {
                                                        setOrders(orders.filter(o => o.order_id !== order.order_id));
                                                    }
                                                } catch (err) {
                                                    console.error("Failed to clear order:", err);
                                                }
                                            }}
                                            className="px-4 py-2 bg-slate-200 hover:bg-slate-300 text-slate-800 text-sm font-bold rounded-lg transition-colors active:scale-95"
                                        >
                                            Clear Order
                                        </button>
                                    )}
                                </div>
                            </div>

                        </div>
                    ))}
                </div>

                {orders.length === 0 && (
                    <div className="text-center py-20 card-base bg-white">
                        <CheckCircle2 className="w-16 h-16 mx-auto mb-4 text-emerald-500" />
                        <p className="text-xl font-bold text-slate-900">All caught up!</p>
                        <p className="mt-2 text-slate-500 font-medium">No active orders in the queue.</p>
                    </div>
                )}

            </div>
        </div>
    );
}
