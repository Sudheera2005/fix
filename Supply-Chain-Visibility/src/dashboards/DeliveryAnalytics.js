import React, { useState, useEffect } from "react";
import api from "../api";
import {
    AreaChart, Area, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer,
    PieChart, Pie, Cell, BarChart, Bar
} from 'recharts';
import {
    TrendingUp, AlertCircle, CheckCircle, Fuel, DollarSign, Activity, RefreshCw,
    Download, Map as MapIcon, Truck, Calendar, ArrowUpRight, ArrowDownRight, AlertTriangle, 
    Zap, Clock, Target, ShieldAlert, BrainCircuit, BarChart3, Filter, FileText,
    Users, Gauge, MapPin
} from "lucide-react";
import toast from "react-hot-toast";

// --- Theme Colors ---
const COLORS = {
    primary: '#4f46e5', // indigo-600
    success: '#10b981', // emerald-500
    warning: '#f59e0b', // amber-500
    danger: '#ef4444',  // rose-500
    info: '#3b82f6',    // blue-500
    slate: '#64748b'    // slate-500
};
const PIE_COLORS = ['#4f46e5', '#3b82f6', '#0ea5e9', '#38bdf8', '#7dd3fc'];
const FAIL_COLORS = ['#ef4444', '#f97316', '#f59e0b', '#fbbf24'];

// --- Mock Data Generators for Advanced Modules ---
const MOCK_PREDICTIVE_DATA = Array.from({length: 7}).map((_, i) => ({
    time: `${i+8}:00`,
    expected_volume: Math.floor(Math.random() * 50) + 100,
    delay_probability: Math.floor(Math.random() * 30) + 10,
    actual_volume: i < 4 ? Math.floor(Math.random() * 40) + 90 : null
}));

const MOCK_FINANCIALS = {
    cost_breakdown: [
        { name: 'Fuel', value: 4500 },
        { name: 'Maintenance', value: 2100 },
        { name: 'Driver Overtime', value: 1200 },
        { name: 'Tolls & Fees', value: 500 }
    ],
    avg_cost_trend: [4.2, 4.1, 4.3, 3.9, 3.8, 4.0, 3.7]
};

const MOCK_RISKS = [
    { id: 1, type: 'critical', title: 'Severe Congestion', desc: 'Colombo North route experiencing 45m delays.', metric: '45m delay' },
    { id: 2, type: 'warning', title: 'Vehicle Maintenance', desc: 'Fleet Asset #22 engine temp abnormal.', metric: 'Temp High' },
    { id: 3, type: 'warning', title: 'Driver Overload', desc: '3 drivers exceeding 9hr shift limit.', metric: 'Compliance' },
];

const MOCK_SPARKLINE_DATA = Array.from({length: 10}).map(() => ({ val: Math.random() * 100 }));

export default function DeliveryAnalytics() {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [isFilterOpen, setIsFilterOpen] = useState(false);
    
    // UI State
    const [filters, setFilters] = useState({ date_from: '', date_to: '', region: 'all' });

    const fetchAnalytics = React.useCallback(async () => {
        setLoading(true);
        try {
            const res = await api.get('reports/delivery_analytics/');
            setData(res.data);
        } catch (error) {
            toast.error("Failed to load live analytics data");
        }
        setLoading(false);
    }, []);

    useEffect(() => {
        fetchAnalytics();
    }, [fetchAnalytics]);

    if (loading && !data) return (
        <div className="flex items-center justify-center h-[60vh]">
            <div className="flex flex-col items-center gap-4">
                <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-indigo-600"></div>
                <p className="text-slate-500 font-bold text-xs uppercase tracking-[0.2em] animate-pulse">Aggregating Intelligence...</p>
            </div>
        </div>
    );

    if (!data) return null;

    const { summary, trends, failures, driver_performance } = data;

    return (
        <div className="space-y-6 animate-fade-in pb-20 font-sans">
            {/* Executive Header */}
            <div className="flex flex-col xl:flex-row xl:items-end justify-between gap-6 mb-8">
                <div>
                    <h1 className="text-3xl font-black text-slate-900 tracking-tight">Delivery Intelligence</h1>
                    <p className="text-slate-500 font-medium text-sm mt-1 flex items-center gap-2">
                        <Target size={16} className="text-indigo-500" />
                        Executive Dashboard & Decision Support System
                    </p>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                    <button onClick={() => setIsFilterOpen(!isFilterOpen)} className={`flex items-center gap-2 px-5 py-2.5 rounded-xl font-bold text-xs transition-all border ${isFilterOpen ? 'bg-indigo-50 border-indigo-200 text-indigo-700' : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'}`}>
                        <Filter size={16} /> Filters
                    </button>
                    <div className="flex bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
                        <button className="flex items-center gap-2 px-5 py-2.5 text-xs font-bold text-slate-600 hover:bg-slate-50 hover:text-indigo-600 transition-all border-r border-slate-200">
                            <FileText size={16} /> PDF
                        </button>
                        <button className="flex items-center gap-2 px-5 py-2.5 text-xs font-bold text-slate-600 hover:bg-slate-50 hover:text-emerald-600 transition-all">
                            <Download size={16} /> CSV
                        </button>
                    </div>
                    <button onClick={fetchAnalytics} className="p-2.5 bg-slate-900 text-white rounded-xl hover:bg-slate-800 transition-all shadow-md active:scale-95 group">
                        <RefreshCw size={18} className={loading ? 'animate-spin' : 'group-hover:rotate-180 transition-transform duration-500'} />
                    </button>
                </div>
            </div>

            {/* Filter Panel */}
            {isFilterOpen && (
                <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm mb-6 animate-in slide-in-from-top-4 fade-in duration-300">
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                        <div>
                            <label className="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2 block">Date Range</label>
                            <div className="flex gap-2">
                                <input type="date" className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-xs font-medium text-slate-700 focus:ring-2 focus:ring-indigo-500/20 outline-none" />
                            </div>
                        </div>
                        <div>
                            <label className="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2 block">Region</label>
                            <select className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-xs font-medium text-slate-700 focus:ring-2 focus:ring-indigo-500/20 outline-none">
                                <option>All Regions</option>
                                <option>North Zone</option>
                                <option>South Zone</option>
                                <option>CBD Area</option>
                            </select>
                        </div>
                        <div>
                            <label className="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2 block">Retailer Focus</label>
                            <select className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-xs font-medium text-slate-700 focus:ring-2 focus:ring-indigo-500/20 outline-none">
                                <option>All Retailers</option>
                                <option>Key Accounts</option>
                                <option>Small Merchants</option>
                            </select>
                        </div>
                        <div className="flex items-end">
                            <button className="w-full bg-indigo-600 text-white rounded-lg px-4 py-2 text-xs font-bold shadow-sm hover:bg-indigo-700 transition-all">
                                Apply Intelligence Filters
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* AI Recommendations Panel */}
            <div className="bg-gradient-to-r from-indigo-900 to-slate-900 rounded-[24px] p-6 shadow-xl relative overflow-hidden group">
                <div className="absolute top-0 right-0 p-8 opacity-10 group-hover:scale-110 transition-transform duration-700">
                    <BrainCircuit size={120} className="text-indigo-300" />
                </div>
                <div className="relative z-10">
                    <div className="flex items-center gap-3 mb-5">
                        <div className="bg-indigo-500/20 p-2 rounded-lg backdrop-blur-md border border-indigo-400/30">
                            <Zap size={20} className="text-indigo-300" />
                        </div>
                        <h2 className="text-lg font-black text-white tracking-tight">Smart Operational Recommendations</h2>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div className="bg-white/10 backdrop-blur-md border border-white/10 p-4 rounded-xl hover:bg-white/15 transition-colors cursor-pointer">
                            <p className="text-[10px] font-black uppercase text-indigo-300 tracking-widest mb-1">Route Optimization</p>
                            <p className="text-sm font-medium text-white mb-3">Re-route 4 vehicles in CBD Area to avoid predicted 4:00 PM congestion.</p>
                            <span className="text-[10px] font-bold text-emerald-400 flex items-center gap-1"><TrendingUp size={12} /> Saves ~45 mins</span>
                        </div>
                        <div className="bg-white/10 backdrop-blur-md border border-white/10 p-4 rounded-xl hover:bg-white/15 transition-colors cursor-pointer">
                            <p className="text-[10px] font-black uppercase text-rose-300 tracking-widest mb-1">Resource Reallocation</p>
                            <p className="text-sm font-medium text-white mb-3">Assign 2 standby drivers to North Zone to prevent SLA breaches today.</p>
                            <span className="text-[10px] font-bold text-emerald-400 flex items-center gap-1"><TrendingUp size={12} /> Protects 95% SLA</span>
                        </div>
                        <div className="bg-white/10 backdrop-blur-md border border-white/10 p-4 rounded-xl hover:bg-white/15 transition-colors cursor-pointer">
                            <p className="text-[10px] font-black uppercase text-amber-300 tracking-widest mb-1">Cost Reduction</p>
                            <p className="text-sm font-medium text-white mb-3">Consolidate 12 low-volume drops into tomorrow's scheduled run.</p>
                            <span className="text-[10px] font-bold text-emerald-400 flex items-center gap-1"><TrendingUp size={12} /> Est. Savings: $142</span>
                        </div>
                    </div>
                </div>
            </div>

            {/* Executive KPIs */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <ExecutiveMetricCard 
                    title="Delivery Success Rate" 
                    value={`${summary.on_time_rate}%`} 
                    trend={+2.4} 
                    icon={CheckCircle} 
                    color="success" 
                    sparklineData={MOCK_SPARKLINE_DATA}
                />
                <ExecutiveMetricCard 
                    title="Avg Cost / Delivery" 
                    value={`$${summary.avg_cost_per_delivery}`} 
                    trend={-5.2} 
                    trendLabel="vs last week"
                    icon={DollarSign} 
                    color="primary" 
                    sparklineData={MOCK_SPARKLINE_DATA}
                    reverseTrend={true} // lower is better
                />
                <ExecutiveMetricCard 
                    title="Avg Route Time" 
                    value="42m" 
                    trend={+1.5} 
                    icon={Clock} 
                    color="warning" 
                    sparklineData={MOCK_SPARKLINE_DATA}
                    reverseTrend={true}
                />
                <ExecutiveMetricCard 
                    title="Fleet Utilization" 
                    value="82%" 
                    trend={+4.1} 
                    icon={Gauge} 
                    color="info" 
                    sparklineData={MOCK_SPARKLINE_DATA}
                />
            </div>

            {/* Main Grid: Row 1 */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Predictive Trends */}
                <div className="lg:col-span-2 bg-white rounded-[24px] p-6 border border-slate-200 shadow-sm flex flex-col">
                    <div className="flex items-center justify-between mb-6">
                        <div>
                            <h3 className="text-lg font-black text-slate-900 tracking-tight">Predictive Operational Volume</h3>
                            <p className="text-xs text-slate-500 font-medium mt-1">Forecasted vs Actual delivery capacity demands.</p>
                        </div>
                        <div className="flex gap-4 text-[10px] font-bold uppercase tracking-widest bg-slate-50 px-3 py-1.5 rounded-lg">
                            <span className="flex items-center gap-1.5 text-slate-600"><span className="w-2 h-2 rounded-full bg-indigo-500"></span> Expected</span>
                            <span className="flex items-center gap-1.5 text-slate-600"><span className="w-2 h-2 rounded-full bg-emerald-500"></span> Actual</span>
                        </div>
                    </div>
                    <div className="flex-1 min-h-[300px]">
                        <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                            <AreaChart data={MOCK_PREDICTIVE_DATA} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                                <defs>
                                    <linearGradient id="colorExpected" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor={COLORS.primary} stopOpacity={0.2}/>
                                        <stop offset="95%" stopColor={COLORS.primary} stopOpacity={0}/>
                                    </linearGradient>
                                    <linearGradient id="colorActual" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor={COLORS.success} stopOpacity={0.2}/>
                                        <stop offset="95%" stopColor={COLORS.success} stopOpacity={0}/>
                                    </linearGradient>
                                </defs>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                                <XAxis dataKey="time" axisLine={false} tickLine={false} tick={{ fontSize: 10, fontWeight: 700, fill: '#64748b' }} dy={10} />
                                <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 10, fontWeight: 700, fill: '#64748b' }} />
                                <RechartsTooltip contentStyle={{ borderRadius: '12px', border: '1px solid #e2e8f0', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)', fontSize: '12px', fontWeight: 'bold' }} />
                                <Area type="monotone" dataKey="expected_volume" stroke={COLORS.primary} strokeWidth={3} fillOpacity={1} fill="url(#colorExpected)" />
                                <Area type="monotone" dataKey="actual_volume" stroke={COLORS.success} strokeWidth={3} fillOpacity={1} fill="url(#colorActual)" />
                            </AreaChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* Risk Alerts */}
                <div className="bg-white rounded-[24px] p-6 border border-slate-200 shadow-sm flex flex-col">
                    <div className="flex items-center justify-between mb-6">
                        <h3 className="text-lg font-black text-slate-900 tracking-tight">Active Risk Radar</h3>
                        <div className="w-8 h-8 rounded-full bg-rose-50 flex items-center justify-center text-rose-500 animate-pulse">
                            <ShieldAlert size={16} />
                        </div>
                    </div>
                    <div className="space-y-4 flex-1">
                        {MOCK_RISKS.map(risk => (
                            <div key={risk.id} className="p-4 rounded-xl border border-slate-100 bg-slate-50/50 hover:bg-slate-50 transition-colors group">
                                <div className="flex justify-between items-start mb-2">
                                    <div className="flex items-center gap-2">
                                        <div className={`w-2 h-2 rounded-full ${risk.type === 'critical' ? 'bg-rose-500 shadow-[0_0_8px_rgba(239,68,68,0.5)]' : 'bg-amber-500'}`}></div>
                                        <span className={`text-[10px] font-black uppercase tracking-widest ${risk.type === 'critical' ? 'text-rose-600' : 'text-amber-600'}`}>{risk.type}</span>
                                    </div>
                                    <span className="text-xs font-bold text-slate-700 bg-white px-2 py-1 rounded shadow-sm border border-slate-100">{risk.metric}</span>
                                </div>
                                <h4 className="text-sm font-black text-slate-900 leading-tight mb-1">{risk.title}</h4>
                                <p className="text-xs font-medium text-slate-500">{risk.desc}</p>
                            </div>
                        ))}
                    </div>
                    <button className="w-full mt-4 py-3 bg-white border border-slate-200 text-slate-600 rounded-xl text-xs font-bold hover:bg-slate-50 transition-all shadow-sm">
                        View All Operations Logs
                    </button>
                </div>
            </div>

            {/* Main Grid: Row 2 */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                
                {/* Financial Intelligence */}
                <div className="bg-white rounded-[24px] p-6 border border-slate-200 shadow-sm">
                    <h3 className="text-lg font-black text-slate-900 tracking-tight mb-1">Financial Intelligence</h3>
                    <p className="text-xs text-slate-500 font-medium mb-6">Operational cost breakdown (Week).</p>
                    
                    <div className="h-[200px] mb-4 relative">
                        <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                            <PieChart>
                                <Pie data={MOCK_FINANCIALS.cost_breakdown} cx="50%" cy="50%" innerRadius={60} outerRadius={80} paddingAngle={2} dataKey="value">
                                    {MOCK_FINANCIALS.cost_breakdown.map((entry, index) => (
                                        <Cell key={`cell-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                                    ))}
                                </Pie>
                                <RechartsTooltip contentStyle={{ borderRadius: '12px', border: '1px solid #e2e8f0', fontSize: '12px', fontWeight: 'bold' }} />
                            </PieChart>
                        </ResponsiveContainer>
                        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                            <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Total Ops</span>
                            <span className="text-xl font-black text-slate-900">$8.3K</span>
                        </div>
                    </div>
                    
                    <div className="space-y-3">
                        {MOCK_FINANCIALS.cost_breakdown.map((item, i) => (
                            <div key={i} className="flex items-center justify-between p-2.5 rounded-lg bg-slate-50 hover:bg-slate-100 transition-colors">
                                <div className="flex items-center gap-3">
                                    <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: PIE_COLORS[i % PIE_COLORS.length] }}></div>
                                    <span className="text-xs font-bold text-slate-700">{item.name}</span>
                                </div>
                                <span className="text-xs font-black text-slate-900">${item.value}</span>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Failure Root Cause Analysis */}
                <div className="bg-white rounded-[24px] p-6 border border-slate-200 shadow-sm">
                    <div className="flex justify-between items-center mb-6">
                        <div>
                            <h3 className="text-lg font-black text-slate-900 tracking-tight">Failure Root Causes</h3>
                            <p className="text-xs text-slate-500 font-medium mt-1">Analysis of delayed/failed drops.</p>
                        </div>
                        <div className="p-2 bg-rose-50 text-rose-500 rounded-lg"><AlertCircle size={18}/></div>
                    </div>
                    
                    <div className="space-y-4">
                        {failures && failures.filter(f => !['no_answer'].includes(f.exception_type)).slice(0,4).map((f, i) => {
                            const maxCount = Math.max(...failures.map(x => x.count));
                            const pct = (f.count / maxCount) * 100;
                            return (
                                <div key={i} className="space-y-2">
                                    <div className="flex justify-between items-end">
                                        <span className="text-xs font-bold text-slate-700 capitalize">{f.exception_type.replace(/_/g, ' ')}</span>
                                        <span className="text-xs font-black text-slate-900">{f.count} cases</span>
                                    </div>
                                    <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
                                        <div className="h-full rounded-full transition-all duration-1000" style={{ width: `${pct}%`, backgroundColor: FAIL_COLORS[i % FAIL_COLORS.length] }}></div>
                                    </div>
                                </div>
                            )
                        })}
                        {(!failures || failures.length === 0) && (
                             <div className="py-10 text-center text-slate-400 text-xs font-bold uppercase tracking-widest">
                                 No exceptions recorded
                             </div>
                        )}
                    </div>
                    
                    <div className="mt-6 p-4 bg-amber-50 rounded-xl border border-amber-100/50 flex items-start gap-3">
                        <AlertTriangle size={16} className="text-amber-500 shrink-0 mt-0.5" />
                        <p className="text-[11px] font-bold text-amber-800 leading-relaxed">
                            Weather-related delays increased by 14% this week. Consider proactive routing via Highway A2.
                        </p>
                    </div>
                </div>

                {/* Driver & Fleet Intelligence */}
                <div className="bg-white rounded-[24px] p-6 border border-slate-200 shadow-sm">
                    <div className="flex justify-between items-center mb-6">
                        <div>
                            <h3 className="text-lg font-black text-slate-900 tracking-tight">Workforce Efficiency</h3>
                            <p className="text-xs text-slate-500 font-medium mt-1">Top performing personnel ranking.</p>
                        </div>
                        <div className="p-2 bg-indigo-50 text-indigo-500 rounded-lg"><Users size={18}/></div>
                    </div>
                    
                    <div className="space-y-4">
                        {driver_performance && driver_performance.slice(0, 4).map((d, i) => {
                            const rate = Math.round((d.completed_trips / d.total_trips) * 100) || 0;
                            return (
                                <div key={i} className="flex items-center justify-between p-3 rounded-xl hover:bg-slate-50 transition-colors border border-transparent hover:border-slate-100">
                                    <div className="flex items-center gap-3">
                                        <div className={`w-8 h-8 rounded-lg flex items-center justify-center font-black text-[10px] ${i === 0 ? 'bg-amber-100 text-amber-700' : i === 1 ? 'bg-slate-200 text-slate-600' : i === 2 ? 'bg-amber-900/10 text-amber-800' : 'bg-slate-100 text-slate-500'}`}>
                                            #{i + 1}
                                        </div>
                                        <div>
                                            <p className="text-xs font-black text-slate-900">{d.driver__employee__full_name || "Unknown"}</p>
                                            <p className="text-[10px] font-bold text-slate-500">{d.total_trips} Total Routes</p>
                                        </div>
                                    </div>
                                    <div className="text-right">
                                        <p className={`text-xs font-black ${rate >= 90 ? 'text-emerald-600' : rate >= 75 ? 'text-amber-500' : 'text-rose-500'}`}>
                                            {rate}%
                                        </p>
                                        <p className="text-[9px] font-bold uppercase tracking-widest text-slate-400">Success</p>
                                    </div>
                                </div>
                            )
                        })}
                    </div>
                    
                    <button className="w-full mt-4 py-3 bg-white border border-slate-200 text-indigo-600 rounded-xl text-xs font-bold hover:bg-indigo-50 transition-all shadow-sm">
                        View Complete Leaderboard
                    </button>
                </div>
            </div>
        </div>
    );
}

// --- Reusable Executive Metric Card ---
function ExecutiveMetricCard({ title, value, trend, trendLabel, icon: Icon, color, sparklineData, reverseTrend }) {
    const colorThemes = {
        primary: { bg: 'bg-indigo-50', icon: 'text-indigo-600', stroke: '#4f46e5' },
        success: { bg: 'bg-emerald-50', icon: 'text-emerald-600', stroke: '#10b981' },
        warning: { bg: 'bg-amber-50', icon: 'text-amber-600', stroke: '#f59e0b' },
        danger: { bg: 'bg-rose-50', icon: 'text-rose-600', stroke: '#ef4444' },
        info: { bg: 'bg-blue-50', icon: 'text-blue-600', stroke: '#3b82f6' },
    };
    
    const theme = colorThemes[color];
    const isPositiveTrend = trend > 0;
    const isGoodTrend = reverseTrend ? !isPositiveTrend : isPositiveTrend;
    const TrendIcon = isPositiveTrend ? ArrowUpRight : ArrowDownRight;

    return (
        <div className="bg-white p-5 rounded-[24px] border border-slate-200 shadow-sm hover:shadow-md transition-shadow relative overflow-hidden group">
            <div className="flex justify-between items-start mb-4">
                <div className={`p-2.5 rounded-xl ${theme.bg} ${theme.icon} group-hover:scale-110 transition-transform duration-300`}>
                    <Icon size={20} strokeWidth={2.5} />
                </div>
                <div className={`flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-black ${isGoodTrend ? 'bg-emerald-50 text-emerald-600' : 'bg-rose-50 text-rose-600'}`}>
                    <TrendIcon size={12} strokeWidth={3} />
                    {Math.abs(trend)}%
                </div>
            </div>
            
            <div className="mb-4">
                <p className="text-[11px] font-bold text-slate-500 uppercase tracking-widest mb-1">{title}</p>
                <h3 className="text-3xl font-black text-slate-900 tracking-tight">{value}</h3>
            </div>
            
            <div className="h-8 w-full opacity-60 group-hover:opacity-100 transition-opacity">
                <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                    <LineChart data={sparklineData}>
                        <Line type="monotone" dataKey="val" stroke={theme.stroke} strokeWidth={2} dot={false} isAnimationActive={false} />
                    </LineChart>
                </ResponsiveContainer>
            </div>
            
            {trendLabel && <p className="text-[9px] font-bold text-slate-400 text-right mt-1">{trendLabel}</p>}
        </div>
    );
}
