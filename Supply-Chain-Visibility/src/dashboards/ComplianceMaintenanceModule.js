import React, { useState, useEffect, useMemo } from "react";
import api from "../api";
import { ShieldAlert, Bell, Search, AlertTriangle, FileText, CheckCircle2, Calendar, AlertCircle, ChevronDown, ShieldCheck, MoreVertical, Check, Eye, User } from "lucide-react";
import toast from "react-hot-toast";

const getProgressAndRisk = (expiryDateString) => {
    if (!expiryDateString) return { progress: 0, risk: 'Critical', color: 'bg-rose-500', text: 'text-rose-700', bg: 'bg-rose-50', border: 'border-rose-200', label: 'Missing' };
    
    const expiryDate = new Date(expiryDateString);
    const today = new Date();
    const diffTime = expiryDate - today;
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    
    const progress = Math.max(0, Math.min(100, (diffDays / 365) * 100));
    
    if (diffDays < 0) return { progress: 0, risk: 'Critical', days: diffDays, color: 'bg-rose-500', text: 'text-rose-700', bg: 'bg-rose-50', border: 'border-rose-300', label: 'Expired' };
    if (diffDays <= 14) return { progress, risk: 'High', days: diffDays, color: 'bg-orange-500', text: 'text-orange-700', bg: 'bg-orange-50', border: 'border-orange-300', label: 'Expires Soon' };
    if (diffDays <= 30) return { progress, risk: 'Medium', days: diffDays, color: 'bg-amber-500', text: 'text-amber-700', bg: 'bg-amber-50', border: 'border-amber-300', label: 'Approaching' };
    return { progress, risk: 'Low', days: diffDays, color: 'bg-emerald-500', text: 'text-emerald-700', bg: 'bg-emerald-50', border: 'border-emerald-200', label: 'Compliant' };
};

const getOverallRisk = (items) => {
    const risks = items.map(i => getProgressAndRisk(i.expiry).risk);
    if (risks.includes('Critical')) return 'Critical';
    if (risks.includes('High')) return 'High';
    if (risks.includes('Medium')) return 'Medium';
    return 'Low';
};

const riskColors = {
    Critical: 'bg-rose-100 text-rose-700 border-rose-200',
    High: 'bg-orange-100 text-orange-700 border-orange-200',
    Medium: 'bg-amber-100 text-amber-700 border-amber-200',
    Low: 'bg-emerald-100 text-emerald-700 border-emerald-200'
};

export default function ComplianceMaintenanceModule() {
    const [vehicles, setVehicles] = useState([]);
    const [drivers, setDrivers] = useState([]);
    const [loading, setLoading] = useState(true);
    
    // Filters
    const [searchQuery, setSearchQuery] = useState("");
    const [statusFilter, setStatusFilter] = useState("All");
    const [deptFilter, setDeptFilter] = useState("All");
    const [riskFilter, setRiskFilter] = useState("All");
    const [sortOrder, setSortOrder] = useState("Nearest Due");

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        setLoading(true);
        try {
            const [vehRes, userRes] = await Promise.all([
                api.get('vehicles/'),
                api.get('users/')
            ]);
            setVehicles(vehRes.data);
            
            const driverData = userRes.data
                .filter(u => u.role === 'driver')
                .map(u => ({
                    driver_id: u.id,
                    employee: u.employee,
                    license_number: u.driver_profile?.license_number || 'N/A',
                    license_expiry_date: u.driver_profile?.license_expiry_date
                }));
            setDrivers(driverData);
        } catch (err) {
            toast.error("Failed to load compliance data");
        } finally {
            setLoading(false);
        }
    };

    const triggerNotification = async (type, id, name) => {
        try {
            toast.loading("Dispatching notification...");
            await api.post('trigger-reminder/', { type, id });
            toast.dismiss();
            toast.success(`Renewal reminder sent to ${name}`);
        } catch (err) {
            toast.dismiss();
            toast.error(err.response?.data?.error || "Failed to send notification");
        }
    };

    const handleMockAction = (actionName) => {
        toast.success(`${actionName} action completed successfully`);
    };

    const records = useMemo(() => {
        const arr = [];
        vehicles.forEach(v => {
            const validItems = [
                { name: 'Registration', expiry: v.registration_expiry },
                { name: 'Insurance', expiry: v.insurance_expiry },
                { name: 'Maintenance', expiry: v.next_service_date }
            ].filter(item => item.expiry);

            if (validItems.length > 0) {
                arr.push({
                    id: `veh_${v.id}`,
                    type: 'vehicle',
                    db_id: v.id,
                    title: v.plate_number,
                    subtitle: `${v.manufacturer || ''} ${v.model || ''}`.trim() || 'Unknown Asset',
                    department: 'Fleet Management',
                    assigned_to: drivers.find(d => d.driver_id === v.assignedDriver)?.employee?.full_name || 'Unassigned',
                    items: validItems
                });
            }
        });

        drivers.forEach(d => {
            const validItems = [
                { name: 'Driver License', expiry: d.license_expiry_date }
            ].filter(item => item.expiry);

            if (validItems.length > 0) {
                arr.push({
                    id: `drv_${d.driver_id}`,
                    type: 'driver',
                    db_id: d.driver_id,
                    title: d.employee?.full_name || `Driver #${d.driver_id}`,
                    subtitle: `License: ${d.license_number}`,
                    department: 'Personnel',
                    assigned_to: '-',
                    items: validItems
                });
            }
        });

        return arr.map(r => ({
            ...r,
            overallRisk: getOverallRisk(r.items),
            minDays: Math.min(...r.items.map(i => {
                if (!i.expiry) return -999;
                return Math.ceil((new Date(i.expiry) - new Date()) / (1000 * 60 * 60 * 24));
            }))
        }));
    }, [vehicles, drivers]);

    // Analytics
    const totalRecords = records.length;
    const compliantCount = records.filter(r => r.overallRisk === 'Low').length;
    const pendingCount = records.filter(r => r.overallRisk === 'Medium' || r.overallRisk === 'High').length;
    const overdueCount = records.filter(r => r.overallRisk === 'Critical').length;
    const complianceRate = totalRecords ? Math.round((compliantCount / totalRecords) * 100) : 0;

    // Filtering
    let filteredRecords = records.filter(r => {
        if (searchQuery && !r.title.toLowerCase().includes(searchQuery.toLowerCase()) && !r.subtitle.toLowerCase().includes(searchQuery.toLowerCase())) return false;
        if (deptFilter !== 'All' && r.department !== deptFilter) return false;
        if (riskFilter !== 'All' && r.overallRisk !== riskFilter) return false;
        if (statusFilter === 'Compliant' && r.overallRisk !== 'Low') return false;
        if (statusFilter === 'At Risk' && (r.overallRisk === 'Low' || r.overallRisk === 'Critical')) return false;
        if (statusFilter === 'Overdue' && r.overallRisk !== 'Critical') return false;
        return true;
    });

    // Sorting
    filteredRecords.sort((a, b) => {
        if (sortOrder === 'Nearest Due') return a.minDays - b.minDays;
        if (sortOrder === 'Highest Risk') {
            const riskWeight = { 'Critical': 4, 'High': 3, 'Medium': 2, 'Low': 1 };
            return riskWeight[b.overallRisk] - riskWeight[a.overallRisk];
        }
        if (sortOrder === 'Newest') return b.db_id - a.db_id;
        if (sortOrder === 'Oldest') return a.db_id - b.db_id;
        return 0;
    });

    if (loading) {
        return <div className="p-10 text-center animate-pulse text-slate-400 font-bold tracking-widest uppercase">Initializing Compliance Engine...</div>;
    }

    return (
        <div className="space-y-6 max-w-7xl mx-auto animate-fade-in pb-20">
            {/* Header */}
            <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-4">
                <div>
                    <h1 className="text-3xl font-black text-slate-900 tracking-tight flex items-center gap-3">
                        <ShieldCheck className="text-emerald-600" size={32}/>
                        Compliance & Risk Hub
                    </h1>
                    <p className="text-slate-500 font-medium mt-1 text-sm">Enterprise management of asset and personnel compliance.</p>
                </div>
            </div>

            {/* KPI Analytics Bar */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                <div className="bg-white p-5 rounded-[24px] border border-slate-100 shadow-sm flex flex-col justify-between">
                    <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Total Records</span>
                    <div className="text-3xl font-black text-slate-800 mt-2">{totalRecords}</div>
                </div>
                <div className="bg-emerald-50 p-5 rounded-[24px] border border-emerald-100 shadow-sm flex flex-col justify-between">
                    <span className="text-[10px] font-black text-emerald-600 uppercase tracking-widest">Compliant</span>
                    <div className="text-3xl font-black text-emerald-700 mt-2">{compliantCount}</div>
                </div>
                <div className="bg-amber-50 p-5 rounded-[24px] border border-amber-100 shadow-sm flex flex-col justify-between">
                    <span className="text-[10px] font-black text-amber-600 uppercase tracking-widest">Pending Review</span>
                    <div className="text-3xl font-black text-amber-700 mt-2">{pendingCount}</div>
                </div>
                <div className="bg-rose-50 p-5 rounded-[24px] border border-rose-100 shadow-sm flex flex-col justify-between">
                    <span className="text-[10px] font-black text-rose-600 uppercase tracking-widest">Overdue Issues</span>
                    <div className="text-3xl font-black text-rose-700 mt-2">{overdueCount}</div>
                </div>
                <div className="bg-slate-900 p-5 rounded-[24px] shadow-lg flex flex-col justify-between relative overflow-hidden">
                    <div className="absolute top-0 right-0 p-4 opacity-10"><ShieldAlert size={64} className="text-white" /></div>
                    <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest relative z-10">Compliance Rate</span>
                    <div className="text-3xl font-black text-white mt-2 relative z-10">{complianceRate}%</div>
                </div>
            </div>

            {/* Filter Bar */}
            <div className="bg-white p-4 rounded-[24px] border border-slate-100 shadow-sm flex flex-wrap items-center gap-4">
                <div className="relative flex-1 min-w-[200px]">
                    <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                    <input 
                        type="text" 
                        placeholder="Search records..." 
                        value={searchQuery}
                        onChange={e => setSearchQuery(e.target.value)}
                        className="w-full bg-slate-50 border-none rounded-xl pl-12 pr-4 py-3 text-sm font-medium focus:ring-2 focus:ring-indigo-500 outline-none"
                    />
                </div>
                <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className="bg-slate-50 border-none rounded-xl px-4 py-3 text-sm font-bold text-slate-700 outline-none cursor-pointer">
                    <option value="All">All Status</option>
                    <option value="Compliant">Compliant</option>
                    <option value="At Risk">At Risk</option>
                    <option value="Overdue">Overdue</option>
                </select>
                <select value={deptFilter} onChange={e => setDeptFilter(e.target.value)} className="bg-slate-50 border-none rounded-xl px-4 py-3 text-sm font-bold text-slate-700 outline-none cursor-pointer">
                    <option value="All">All Departments</option>
                    <option value="Fleet Management">Fleet Management</option>
                    <option value="Personnel">Personnel</option>
                </select>
                <select value={riskFilter} onChange={e => setRiskFilter(e.target.value)} className="bg-slate-50 border-none rounded-xl px-4 py-3 text-sm font-bold text-slate-700 outline-none cursor-pointer">
                    <option value="All">All Risks</option>
                    <option value="Critical">Critical</option>
                    <option value="High">High</option>
                    <option value="Medium">Medium</option>
                    <option value="Low">Low</option>
                </select>
                <select value={sortOrder} onChange={e => setSortOrder(e.target.value)} className="bg-slate-50 border-none rounded-xl px-4 py-3 text-sm font-bold text-slate-700 outline-none cursor-pointer">
                    <option value="Nearest Due">Sort: Nearest Due</option>
                    <option value="Highest Risk">Sort: Highest Risk</option>
                    <option value="Newest">Sort: Newest</option>
                    <option value="Oldest">Sort: Oldest</option>
                </select>
            </div>

            {/* Cards Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {filteredRecords.map(record => (
                    <div key={record.id} className={`bg-white rounded-[24px] border shadow-sm flex flex-col overflow-hidden transition-all hover:shadow-xl ${record.overallRisk === 'Critical' ? 'border-rose-200 shadow-rose-100' : 'border-slate-100'}`}>
                        {/* Card Header */}
                        <div className="p-6 border-b border-slate-50">
                            <div className="flex justify-between items-start mb-4">
                                <span className="bg-slate-100 text-slate-600 text-[10px] font-black px-2.5 py-1 rounded-md uppercase tracking-widest">{record.department}</span>
                                <span className={`px-2.5 py-1 rounded-md text-[10px] font-black uppercase tracking-widest border ${riskColors[record.overallRisk]}`}>
                                    {record.overallRisk} Risk
                                </span>
                            </div>
                            <h3 className="text-xl font-black text-slate-900 tracking-tight">{record.title}</h3>
                            <p className="text-xs font-medium text-slate-500 mt-1">{record.subtitle}</p>
                            
                            {record.type === 'vehicle' && (
                                <div className="mt-4 flex items-center gap-2 text-xs font-bold text-slate-600 bg-slate-50 w-max px-3 py-1.5 rounded-lg border border-slate-100">
                                    <User size={12}/> Assigned: {record.assigned_to}
                                </div>
                            )}
                        </div>

                        {/* Card Body (Progress) */}
                        <div className="p-6 flex-1 space-y-6">
                            {record.items.map((item, idx) => {
                                const st = getProgressAndRisk(item.expiry);
                                return (
                                    <div key={idx} className="space-y-2">
                                        <div className="flex justify-between items-end">
                                            <span className="text-xs font-bold text-slate-700">{item.name}</span>
                                            <span className={`text-[10px] font-black px-2 py-0.5 rounded uppercase tracking-widest ${st.text} ${st.bg}`}>{st.label}</span>
                                        </div>
                                        <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
                                            <div className={`h-full rounded-full ${st.color}`} style={{ width: `${st.progress}%` }}></div>
                                        </div>
                                        <div className="flex justify-between text-[10px] font-bold text-slate-400">
                                            <span>{item.expiry || 'Not set'}</span>
                                            <span>{st.progress > 0 ? `${Math.round(st.progress)}% Valid` : '0%'}</span>
                                        </div>
                                    </div>
                                )
                            })}
                        </div>

                        {/* Card Footer (Actions) */}
                        <div className="p-4 bg-slate-50 border-t border-slate-100 flex items-center justify-between">
                            <button 
                                onClick={() => triggerNotification(record.type, record.db_id, record.title)}
                                className="flex-1 bg-white border border-slate-200 hover:border-indigo-500 hover:text-indigo-600 text-slate-700 px-4 py-2.5 rounded-xl text-xs font-black uppercase tracking-widest transition-all shadow-sm flex items-center justify-center gap-2"
                            >
                                <Bell size={14}/> {record.type === 'vehicle' ? 'Request Renewal' : 'Notify Driver'}
                            </button>
                            
                            <div className="relative group ml-3">
                                <button className="w-10 h-10 bg-white border border-slate-200 hover:bg-slate-100 rounded-xl flex items-center justify-center text-slate-500 transition-all shadow-sm">
                                    <MoreVertical size={16} />
                                </button>
                                <div className="absolute right-0 bottom-full mb-2 w-48 bg-white border border-slate-200 shadow-xl rounded-2xl p-2 opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-10 transform translate-y-2 group-hover:translate-y-0">
                                    <button onClick={() => handleMockAction('View Details')} className="w-full text-left px-4 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50 rounded-lg flex items-center gap-2">
                                        <Eye size={14}/> View Details
                                    </button>
                                    <button onClick={() => handleMockAction('Approve Exemption')} className="w-full text-left px-4 py-2 text-xs font-bold text-emerald-600 hover:bg-emerald-50 rounded-lg flex items-center gap-2 mt-1">
                                        <Check size={14}/> Approve Exemption
                                    </button>
                                    <button onClick={() => handleMockAction('Resolve Issue')} className="w-full text-left px-4 py-2 text-xs font-bold text-indigo-600 hover:bg-indigo-50 rounded-lg flex items-center gap-2 mt-1">
                                        <CheckCircle2 size={14}/> Resolve Issue
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                ))}
                
                {filteredRecords.length === 0 && (
                    <div className="col-span-full py-20 flex flex-col items-center justify-center text-slate-400">
                        <ShieldAlert size={48} className="mb-4 opacity-20" />
                        <p className="text-lg font-bold">No compliance records found.</p>
                        <p className="text-sm">Try adjusting your filters or search query.</p>
                    </div>
                )}
            </div>
        </div>
    );
}
