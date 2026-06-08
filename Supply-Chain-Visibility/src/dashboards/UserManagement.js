import { useState, useEffect, useRef } from "react";
import api from "../api";
import { BiUser, BiPlus, BiPencil, BiTrash, BiSearch, BiFilterAlt, BiEnvelope, BiBuilding, BiCreditCard, BiCalendar, BiPhone, BiDownload } from "react-icons/bi";
import { HiOutlineUserGroup } from "react-icons/hi";
import toast from 'react-hot-toast';
import ConfirmationModal from '../UIComponents/ConfirmationModal';

function CreateUserPopup({ onClose }) {
    const [email, setEmail] = useState("");
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [confirmPassword, setConfirmPassword] = useState("");
    const [role, setRole] = useState("driver");
    
    // Universal Employee fields
    const [fullName, setFullName] = useState("");
    const [nationalId, setNationalId] = useState("");
    const [contact, setContact] = useState("");
    const [empAddress, setEmpAddress] = useState("");
    const [dob, setDob] = useState("");

    // Driver conditional fields
    const [licenseId, setLicenseId] = useState("");
    const [licenseExpiry, setLicenseExpiry] = useState("");
    const [licenseType, setLicenseType] = useState("heavy_vehicle");
    const [experienceYears, setExperienceYears] = useState("0");
    
    // Customer conditional fields
    const [businessName, setBusinessName] = useState("");
    const [contactPerson, setContactPerson] = useState("");
    const [taxId, setTaxId] = useState("");
    
    const [loading, setLoading] = useState(false);

    const validateFields = () => {
        if (role !== 'customer') {
            const nicRegex = /^(\d{9}[Vv]|\d{12})$/;
            if (!nicRegex.test(nationalId)) {
                toast.error("National ID must be 9 digits + 'V' or 12 digits.");
                return false;
            }
            const birthDate = new Date(dob);
            const today = new Date();
            let age = today.getFullYear() - birthDate.getFullYear();
            const m = today.getMonth() - birthDate.getMonth();
            if (m < 0 || (m === 0 && today.getDate() < birthDate.getDate())) {
                age--;
            }
            if (age < 18) {
                toast.error("User must be at least 18 years old.");
                return false;
            }
        }
        if (contact.length < 10) {
            toast.error("Telephone must be at least 10 digits.");
            return false;
        }
        if (password !== confirmPassword) {
            toast.error("Passwords do not match.");
            return false;
        }
        if (role === 'driver') {
            if (["123", "abc", "test"].includes(licenseId.toLowerCase())) {
                toast.error("Please provide a valid License ID.");
                return false;
            }
            if (new Date(licenseExpiry) < new Date()) {
                toast.error("License has already expired.");
                return false;
            }
        }
        return true;
    };

    const modalRef = useRef();
    
    useEffect(() => {
        const handleEsc = (e) => { if (e.key === 'Escape') onClose(); };
        window.addEventListener('keydown', handleEsc);
        return () => window.removeEventListener('keydown', handleEsc);
    }, [onClose]);

    const handleOutsideClick = (e) => {
        if (modalRef.current && !modalRef.current.contains(e.target)) {
            onClose();
        }
    };

    const handleCreate = async (e) => {
        e.preventDefault();
        if (!validateFields()) return;
        setLoading(true);
        try {
            const payload = { email, username, password, role };
            if (role === 'customer') {
                payload.customer = {
                    business_name: businessName,
                    contact_person_name: contactPerson,
                    phone_number: contact,
                    address: empAddress,
                    tax_id: taxId
                };
            } else {
                payload.employee = {
                    full_name: fullName,
                    national_id: nationalId,
                    contact_number: contact,
                    address: empAddress,
                    date_of_birth: dob
                };
                if (role === 'driver') {
                    payload.driver_profile = {
                        license_number: licenseId,
                        license_expiry_date: licenseExpiry,
                        license_type: licenseType,
                        experience_years: parseFloat(experienceYears) || 0
                    };
                }
            }
            await api.post('users/', payload);
            toast.success("Identity Provisioned Successfully");
            onClose();
        } catch (error) {
            toast.error(error?.response?.data?.detail || "Registration failed");
        }
        setLoading(false);
    };

    return (
        <div onClick={handleOutsideClick} className="fixed inset-0 bg-[#3E2723]/60 backdrop-blur-md flex items-center justify-center z-50 p-4 transition-all animate-fade-in">
            <div ref={modalRef} className="bg-white p-8 rounded-[32px] shadow-2xl w-full max-w-2xl border border-coffee-100 overflow-hidden flex flex-col max-h-[90vh]">
                <div className="mb-6">
                    <h2 className="text-2xl font-bold text-coffee-900 tracking-tight">Provision Identity</h2>
                    <p className="text-sm text-coffee-500 mt-1">Register a new asset or employee into the logistics ecosystem.</p>
                </div>

                <form onSubmit={handleCreate} className="flex-1 overflow-y-auto pr-2 custom-scrollbar space-y-8">
                    {/* Primary Allocation */}
                    <div className="bg-coffee-50/50 p-5 rounded-2xl border border-coffee-100">
                        <label className="block text-[11px] font-bold text-coffee-400 mb-2 uppercase tracking-widest">Authority Assignment</label>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <select 
                                value={role} 
                                onChange={e => setRole(e.target.value)} 
                                className="w-full bg-white border border-coffee-200 rounded-xl px-4 py-3 text-sm font-semibold text-coffee-700 focus:ring-4 focus:ring-coffee-500/10 focus:border-coffee-500 outline-none transition-all shadow-sm"
                            >
                                <option value="admin">Administrator (System)</option>
                                <option value="manager">Manager (Regional)</option>
                                <option value="dispatcher">Dispatcher (Fleet)</option>
                                <option value="driver">Driver (Logistics)</option>
                                <option value="customer">Corporate Customer</option>
                            </select>
                            <div className="flex items-center px-4 text-xs font-medium text-coffee-500 italic">
                                * Determines system-wide access permissions.
                            </div>
                        </div>
                    </div>

                    {/* Account Credentials */}
                    <div className="space-y-4">
                        <h3 className="text-sm font-bold text-coffee-900 border-l-4 border-coffee-600 pl-3">Security Credentials</h3>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <InputField label="Username" icon={<BiUser/>} value={username} onChange={e => setUsername(e.target.value)} placeholder="j.doe" required />
                            <InputField label="Email Address" icon={<BiEnvelope/>} type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="jane@enterprise.com" required />
                            <InputField label="Password" type="password" value={password} onChange={e => setPassword(e.target.value)} required />
                            <InputField label="Confirm Password" type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} required />
                        </div>
                    </div>

                    {/* Conditional Profiles */}
                    {role === 'customer' ? (
                        <div className="space-y-4 animate-fade-in">
                            <h3 className="text-sm font-bold text-slate-900 border-l-4 border-emerald-500 pl-3 uppercase tracking-wide">Corporate Profile</h3>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                <InputField label="Business Name" icon={<BiBuilding/>} value={businessName} onChange={e => setBusinessName(e.target.value)} />
                                <InputField label="Representative" icon={<BiUser/>} value={contactPerson} onChange={e => setContactPerson(e.target.value)} />
                                <InputField label="Phone" icon={<BiPhone/>} value={contact} onChange={e => setContact(e.target.value)} required />
                                <InputField label="Tax Identity" icon={<BiCreditCard/>} value={taxId} onChange={e => setTaxId(e.target.value)} />
                                <div className="sm:col-span-2">
                                    <InputField label="HQ Address" value={empAddress} onChange={e => setEmpAddress(e.target.value)} required />
                                </div>
                            </div>
                        </div>
                    ) : (
                        <div className="space-y-4 animate-fade-in">
                            <h3 className="text-sm font-bold text-coffee-900 border-l-4 border-coffee-500 pl-3 uppercase tracking-wide">Employment Record</h3>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                <div className="sm:col-span-2">
                                    <InputField label="Full Personnel Name" value={fullName} onChange={e => setFullName(e.target.value)} required />
                                </div>
                                <InputField label="National ID / NIC" icon={<BiCreditCard/>} value={nationalId} onChange={e => setNationalId(e.target.value)} required />
                                <InputField label="Primary Contact" icon={<BiPhone/>} value={contact} onChange={e => setContact(e.target.value)} required />
                                <div className="sm:col-span-2">
                                    <InputField label="Residential Address" value={empAddress} onChange={e => setEmpAddress(e.target.value)} required />
                                </div>
                                <InputField label="Date of Birth" icon={<BiCalendar/>} type="date" value={dob} onChange={e => setDob(e.target.value)} required />
                            </div>
                        </div>
                    )}

                    {role === 'driver' && (
                        <div className="space-y-4 animate-fade-in">
                            <h3 className="text-sm font-bold text-slate-900 border-l-4 border-amber-500 pl-3 uppercase tracking-wide">Field Authorization</h3>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                <InputField label="License ID" value={licenseId} onChange={e => setLicenseId(e.target.value)} required />
                                <InputField label="License Expiry" type="date" value={licenseExpiry} onChange={e => setLicenseExpiry(e.target.value)} required />
                                <div>
                                    <label className="block text-[11px] font-bold text-slate-400 mb-1.5 uppercase tracking-widest">Auth Classification</label>
                                    <select value={licenseType} onChange={e => setLicenseType(e.target.value)} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm font-medium outline-none">
                                        <option value="heavy_vehicle">Heavy Transport (HT)</option>
                                        <option value="light_vehicle">Light Distribution (LD)</option>
                                        <option value="trailer">Articulated Trailer</option>
                                    </select>
                                </div>
                                <InputField label="Total Experience (Yrs)" type="number" step="0.5" value={experienceYears} onChange={e => setExperienceYears(e.target.value)} required />
                            </div>
                        </div>
                    )}
                </form>

                <div className="flex justify-end items-center pt-6 mt-6 border-t border-coffee-100 gap-3">
                    <button type="button" onClick={onClose} className="px-6 py-2.5 text-sm font-bold text-coffee-400 hover:bg-coffee-50 rounded-xl transition-all">Cancel</button>
                    <button 
                        onClick={handleCreate} 
                        disabled={loading} 
                        className="bg-coffee-700 hover:bg-coffee-800 text-white px-8 py-3 rounded-xl shadow-lg shadow-coffee-200 text-sm font-bold transition-all transform active:scale-95 disabled:opacity-70"
                    >
                        {loading ? "Processing..." : "Register Identity"}
                    </button>
                </div>
            </div>
        </div>
    );
}

function InputField({ label, icon, value, onChange, type = "text", placeholder, required = false, step, autoComplete }) {
    return (
        <div>
            <label className="block text-[11px] font-bold text-coffee-400 mb-1.5 uppercase tracking-widest">{label}</label>
            <div className="relative group">
                {icon && <div className="absolute left-4 top-1/2 -translate-y-1/2 text-coffee-400 group-focus-within:text-coffee-600 transition-colors text-lg">{icon}</div>}
                <input 
                    type={type} 
                    value={value} 
                    onChange={onChange} 
                    placeholder={placeholder} 
                    required={required}
                    step={step}
                    autoComplete={autoComplete || (type === 'password' ? 'new-password' : undefined)}
                    className={`w-full bg-coffee-50/30 border border-coffee-100 rounded-xl ${icon ? 'pl-11' : 'px-4'} py-2.5 text-sm font-medium text-coffee-900 focus:ring-4 focus:ring-coffee-500/10 focus:border-coffee-500 outline-none transition-all placeholder-coffee-200`} 
                />
            </div>
        </div>
    );
}

function AssignRolesPopup({ onClose }) {
    const [identifier, setIdentifier] = useState("");
    const [userDoc, setUserDoc] = useState(null);
    const [newRole, setNewRole] = useState("driver");
    const [loading, setLoading] = useState(false);

    const modalRef = useRef();

    useEffect(() => {
        const handleEsc = (e) => { if (e.key === 'Escape') onClose(); };
        window.addEventListener('keydown', handleEsc);
        return () => window.removeEventListener('keydown', handleEsc);
    }, [onClose]);

    const handleOutsideClick = (e) => {
        if (modalRef.current && !modalRef.current.contains(e.target)) {
            onClose();
        }
    };

    const handleSearch = async (e) => {
        e.preventDefault();
        setLoading(true);
        try {
            const res = await api.get('users/');
            const users = res.data;
            const match = users.find(u => u.email === identifier || u.username === identifier);
            if (match) {
                setUserDoc(match);
                setNewRole(match.role);
            } else {
                toast.error("User not found");
                setUserDoc(null);
            }
        } catch (error) {
            toast.error(error.message);
        }
        setLoading(false);
    };

    const handleAssign = async (e) => {
        e.preventDefault();
        try {
            if (!userDoc) return;
            await api.patch(`users/${userDoc.id}/`, { role: newRole });
            toast.success("Security Policy Updated");
            onClose();
        } catch (error) {
            toast.error(error.message);
        }
    };

    return (
        <div onClick={handleOutsideClick} className="fixed inset-0 bg-[#3E2723]/60 backdrop-blur-md flex items-center justify-center z-50 p-4 animate-fade-in">
            <div ref={modalRef} className="bg-white p-8 rounded-[24px] shadow-2xl w-full max-w-md border border-coffee-100 animate-fade-in-up">
                <div className="mb-6">
                    <h2 className="text-2xl font-bold text-coffee-900 tracking-tight">Security & Governance</h2>
                    <p className="text-sm text-coffee-500 mt-1">Elevate or restrict system-wide authorities for a specific user.</p>
                </div>

                {!userDoc ? (
                    <form onSubmit={handleSearch} className="space-y-6">
                        <InputField label="Identity Search" placeholder="Search by email or username..." icon={<BiSearch/>} value={identifier} onChange={e => setIdentifier(e.target.value)} required />
                        <div className="flex justify-end gap-3">
                            <button type="button" onClick={onClose} className="px-5 py-2.5 text-sm font-bold text-coffee-500 hover:bg-coffee-50 rounded-xl transition-all">Cancel</button>
                            <button type="submit" disabled={loading} className="bg-coffee-900 hover:bg-coffee-800 text-white px-6 py-2.5 rounded-xl shadow-lg text-sm font-bold transition-all disabled:opacity-70">
                                {loading ? "Searching..." : "Retrieve Identity"}
                            </button>
                        </div>
                    </form>
                ) : (
                    <form onSubmit={handleAssign} className="space-y-6">
                        <div className="bg-coffee-50 border border-coffee-100 p-5 rounded-2xl relative overflow-hidden">
                           <div className="absolute top-0 right-0 p-3 opacity-10 text-4xl text-coffee-900"><BiUser/></div>
                           <div className="relative z-10">
                                <p className="text-xs font-black text-coffee-400 uppercase tracking-widest mb-2">Authenticated Subject</p>
                                <p className="text-lg font-bold text-coffee-900">{userDoc.username}</p>
                                <p className="text-sm text-coffee-600 font-medium">{userDoc.email}</p>
                                <div className="mt-3 inline-flex items-center bg-white border border-coffee-200 px-3 py-1 rounded-full text-[10px] font-black text-coffee-600 uppercase tracking-widest">
                                    Current: {userDoc.role}
                                </div>
                           </div>
                        </div>

                        <div className="space-y-2">
                            <label className="block text-[11px] font-bold text-coffee-400 mb-2 uppercase tracking-widest">New Role Authorization</label>
                            <select value={newRole} onChange={e => setNewRole(e.target.value)} className="w-full bg-coffee-50 border border-coffee-200 rounded-xl px-4 py-3 text-sm font-bold text-coffee-700 outline-none focus:ring-4 focus:ring-coffee-500/10 focus:border-coffee-500 transition-all">
                                <option value="admin">Administrator (Global Access)</option>
                                <option value="manager">Manager (Fleet Oversight)</option>
                                <option value="dispatcher">Dispatcher (Route Logs)</option>
                                <option value="driver">Driver (Field Portal)</option>
                                <option value="customer">Customer (Order View)</option>
                            </select>
                        </div>

                        {newRole === 'driver' && userDoc.role !== 'driver' && (
                            <div className="p-4 bg-amber-50 border border-amber-100 rounded-2xl flex gap-3 animate-fade-in">
                                <BiCreditCard className="text-amber-600 text-xl shrink-0 mt-0.5"/>
                                <p className="text-[11px] font-black text-amber-800 leading-relaxed uppercase tracking-wider">
                                    Upgrade Notice: Promoting to Driver will automatically initialize a field authorization record. License details must be updated later.
                                </p>
                            </div>
                        )}

                        <div className="flex justify-end gap-3 pt-2">
                            <button type="button" onClick={() => setUserDoc(null)} className="px-5 py-2.5 text-sm font-bold text-coffee-500 hover:bg-coffee-50 rounded-xl transition-all">Back</button>
                            <button type="submit" className="bg-coffee-600 hover:bg-coffee-700 text-white px-8 py-2.5 rounded-xl shadow-lg shadow-coffee-100 text-sm font-bold transition-all">Apply Modification</button>
                        </div>
                    </form>
                )}
            </div>
        </div>
    );
}

export default function UserManagement() {
    const [users, setUsers] = useState([]);
    const [activeAction, setActiveAction] = useState(null);
    const [selectedUser, setSelectedUser] = useState(null);
    const [editTab, setEditTab] = useState('account');
    const [searchQuery, setSearchQuery] = useState("");
    const [isChangingPassword, setIsChangingPassword] = useState(false);
    const [newPassword, setNewPassword] = useState("");
    const [confirmNewPassword, setConfirmNewPassword] = useState("");
    const [deleteTarget, setDeleteTarget] = useState(null);
    const [selectedUserIds, setSelectedUserIds] = useState([]);
    const editModalRef = useRef();

    useEffect(() => {
        const handleEsc = (e) => { 
            if (e.key === 'Escape') {
                setActiveAction(null);
                setIsChangingPassword(false);
            }
        };
        window.addEventListener('keydown', handleEsc);
        return () => window.removeEventListener('keydown', handleEsc);
    }, []);

    const handleOutsideEditClick = (e) => {
        if (editModalRef.current && !editModalRef.current.contains(e.target)) {
            setActiveAction(null);
            setIsChangingPassword(false);
        }
    };

    const fetchUsers = async () => {
        try {
            const res = await api.get('users/');
            setUsers(res.data);
        } catch(e) { console.error(e); }
    };

    useEffect(() => {
        fetchUsers();
    }, []);

    const filteredUsers = users.filter(u => 
        u.username.toLowerCase().includes(searchQuery.toLowerCase()) || 
        u.email.toLowerCase().includes(searchQuery.toLowerCase()) ||
        u.role.toLowerCase().includes(searchQuery.toLowerCase())
    );

    const stats = {
        total: users.length,
        drivers: users.filter(u => u.role === 'driver').length,
        admins: users.filter(u => u.role === 'admin').length,
        active: users.filter(u => u.status !== 'inactive').length
    };

    const toggleSelection = (id) => {
        setSelectedUserIds(prev => 
            prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
        );
    };

    const downloadPdf = async (endpoint, filename) => {
        try {
            const res = await api.get(endpoint, { responseType: 'blob' });
            const url = window.URL.createObjectURL(new Blob([res.data]));
            const link = document.createElement('a');
            link.href = url;
            link.setAttribute('download', filename);
            document.body.appendChild(link);
            link.click();
            link.parentNode.removeChild(link);
        } catch (error) {
            toast.error("Failed to download document. Please check your permissions.");
        }
    };

    const handleBulkDelete = async () => {
        if (window.confirm(`Are you sure you want to delete ${selectedUserIds.length} users?`)) {
            try {
                await Promise.all(selectedUserIds.map(id => api.delete(`users/${id}/`)));
                toast.success("Bulk Operation Successful");
                setSelectedUserIds([]);
                fetchUsers();
            } catch (err) {
                toast.error("Some operations failed");
            }
        }
    };

    return (
        <div className="space-y-8 animate-fade-in pb-20 max-w-7xl mx-auto">
            {/* Header Area */}
            <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
                <div>
                    <h1 className="text-3xl font-black text-coffee-900 tracking-tight">Personnel Directory</h1>
                    <p className="text-coffee-500 font-medium mt-1">Manage global identity provisioning and access control policies.</p>
                </div>
                <div className="flex items-center gap-3">
                    <button
                        className="bg-coffee-700 hover:bg-coffee-800 text-white px-6 py-3 rounded-2xl shadow-lg shadow-coffee-100 text-sm font-bold transition-all flex items-center transform active:scale-95"
                        onClick={() => setActiveAction('CREATE_USER')}
                    >
                        <BiPlus className="mr-2 text-xl" /> Provision User
                    </button>
                    <button
                        className="bg-white hover:bg-coffee-50 text-coffee-700 border border-coffee-200 px-6 py-3 rounded-2xl shadow-sm text-sm font-bold transition-all flex items-center"
                        onClick={() => setActiveAction('ASSIGN_ROLES')}
                    >
                        <BiFilterAlt className="mr-2 text-xl text-coffee-400" /> Policy Manager
                    </button>
                </div>
            </div>

            {/* Quick Stats */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <StatCard label="Total Identities" value={stats.total} icon={<HiOutlineUserGroup/>} color="coffee" />
                <StatCard label="Active Fleet" value={stats.drivers} icon={<BiUser/>} color="emerald" />
                <StatCard label="Administrators" value={stats.admins} icon={<BiUser/>} color="amber" />
                <StatCard label="System Status" value="Healthy" icon={<BiPlus/>} color="blue" />
            </div>

            {/* Main Content Area */}
            <div className="space-y-4">
                {/* Search Bar & Bulk Actions */}
                <div className="flex flex-col md:flex-row gap-4 items-center justify-between">
                    <div className="relative group flex-1 max-w-md w-full">
                        <BiSearch className="absolute left-5 top-1/2 -translate-y-1/2 text-coffee-400 text-xl group-focus-within:text-coffee-600 transition-colors" />
                        <input 
                            type="text" 
                            placeholder="Search by name, email or role..." 
                            value={searchQuery}
                            onChange={e => setSearchQuery(e.target.value)}
                            className="w-full bg-white border border-coffee-100 rounded-[24px] pl-14 pr-6 py-4 text-sm font-medium focus:ring-8 focus:ring-coffee-500/5 focus:border-coffee-500 outline-none transition-all shadow-sm placeholder-coffee-300"
                        />
                    </div>
                    {selectedUserIds.length > 0 && (
                        <div className="flex items-center gap-3 bg-rose-50 border border-rose-100 px-6 py-2 rounded-2xl animate-fade-in-up">
                            <span className="text-xs font-bold text-rose-600 uppercase tracking-widest">{selectedUserIds.length} Selected</span>
                            <button onClick={handleBulkDelete} className="bg-rose-600 text-white p-2 rounded-xl hover:bg-rose-700 transition-all shadow-sm shadow-rose-100">
                                <BiTrash className="text-lg" />
                            </button>
                        </div>
                    )}
                </div>

                {/* Personel List */}
                <div className="space-y-3">
                    {filteredUsers.length > 0 ? (
                        filteredUsers.map(u => (
                            <div key={u.id} className={`bg-white border ${selectedUserIds.includes(u.id) ? 'border-coffee-500 ring-4 ring-coffee-500/5' : 'border-coffee-100'} p-4 sm:p-5 rounded-[28px] flex flex-col sm:flex-row sm:items-center justify-between gap-4 hover:shadow-xl hover:shadow-coffee-100/50 transition-all hover:-translate-y-0.5 group relative`}>
                                <div className="flex items-center gap-4">
                                    <input 
                                        type="checkbox" 
                                        checked={selectedUserIds.includes(u.id)}
                                        onChange={() => toggleSelection(u.id)}
                                        className="w-5 h-5 rounded-lg border-coffee-200 text-coffee-600 focus:ring-coffee-500 cursor-pointer"
                                    />
                                    <div className="w-12 h-12 rounded-2xl bg-coffee-50 border border-coffee-100 flex items-center justify-center text-coffee-400 text-xl group-hover:bg-coffee-100 group-hover:text-coffee-600 transition-colors">
                                        <BiUser />
                                    </div>
                                    <div>
                                        <div className="flex items-center gap-2">
                                            <p className="font-bold text-coffee-950">{u.username}</p>
                                            <span className={`px-2 py-0.5 rounded-md text-[9px] font-black uppercase tracking-tighter border ${getRoleStyles(u.role)}`}>
                                                {u.role}
                                            </span>
                                        </div>
                                        <p className="text-xs text-coffee-500 font-medium">{u.email}</p>
                                    </div>
                                </div>

                                <div className="flex items-center justify-between sm:justify-end gap-6 sm:gap-12 pl-10 sm:pl-0">
                                    <div className="hidden lg:block text-right">
                                        <p className="text-[10px] text-coffee-300 font-bold uppercase tracking-widest mb-1">Personnel ID</p>
                                        <p className="text-sm font-mono font-bold text-coffee-800">#{u.id.toString().padStart(5, '0')}</p>
                                    </div>
                                    
                                    <div>
                                        <StatusBadge status={u.status} />
                                    </div>

                                    <div className="flex items-center gap-2">
                                        {u.role === 'driver' && (
                                            <button 
                                                onClick={() => downloadPdf(`reports/driver_vehicle_history/?target_user_id=${u.id}`, `Driver_History_${u.username}.pdf`)}
                                                className="w-10 h-10 flex items-center justify-center rounded-xl border border-coffee-100 text-coffee-300 hover:text-emerald-600 hover:bg-emerald-50 hover:border-emerald-100 transition-all shadow-sm"
                                                title="Download Monthly Driver Assignment History"
                                            >
                                                <BiDownload />
                                            </button>
                                        )}
                                        <button 
                                            onClick={() => { setSelectedUser(JSON.parse(JSON.stringify(u))); setEditTab('account'); setActiveAction('EDIT_ACCT'); }}
                                            className="w-10 h-10 flex items-center justify-center rounded-xl border border-coffee-100 text-coffee-300 hover:text-coffee-700 hover:bg-coffee-50 hover:border-coffee-200 transition-all shadow-sm"
                                        >
                                            <BiPencil />
                                        </button>
                                        <button 
                                            onClick={async () => {
                                                if (u.role === 'driver') {
                                                    try {
                                                        const res = await api.get('vehicles/');
                                                        const userVehicles = res.data.filter(v => v.driver_name === u.username || v.assignedDriver === u.id);
                                                        if (userVehicles.some(v => (v.current_load_weight || 0) > 0)) {
                                                            toast.error("Cannot delete: Driver is assigned to an active shipment.");
                                                            return;
                                                        }
                                                        if (userVehicles.length > 0) {
                                                            setDeleteTarget({...u, boundVehicleId: userVehicles[0].id});
                                                            return;
                                                        }
                                                    } catch (e) {
                                                        // Fallback
                                                    }
                                                }
                                                setDeleteTarget(u);
                                            }}
                                            className="w-10 h-10 flex items-center justify-center rounded-xl border border-coffee-100 text-coffee-300 hover:text-rose-600 hover:bg-rose-50 hover:border-rose-100 transition-all shadow-sm"
                                        >
                                            <BiTrash />
                                        </button>
                                    </div>
                                </div>
                            </div>
                        ))
                    ) : (
                        <div className="bg-white border-2 border-dashed border-coffee-100 rounded-[40px] p-20 flex flex-col items-center justify-center text-center">
                            <div className="w-20 h-20 bg-coffee-50 rounded-3xl flex items-center justify-center mb-4">
                                <BiUser className="text-4xl text-coffee-200" />
                            </div>
                            <h3 className="text-lg font-bold text-coffee-900">No personnel found</h3>
                            <p className="text-sm text-coffee-500 mt-1 max-w-xs">We couldn't find any users matching your current search criteria.</p>
                        </div>
                    )}
                </div>
            </div>

            {/* Modals & Popups */}
            {activeAction === 'EDIT_ACCT' && selectedUser && (
                <div onClick={handleOutsideEditClick} className="fixed inset-0 bg-slate-900/60 backdrop-blur-md flex items-center justify-center z-50 p-4 animate-fade-in">
                    <div ref={editModalRef} className="bg-white p-8 rounded-[32px] shadow-2xl w-full max-w-xl border border-slate-200 animate-fade-in-up">
                        <div className="mb-6">
                            <h2 className="text-2xl font-bold text-slate-900 tracking-tight">Modify Identity</h2>
                            <p className="text-sm text-slate-500 mt-1">Update authentication data and personnel records.</p>
                        </div>
                        
                        <div className="flex gap-2 p-1.5 bg-slate-100 rounded-2xl mb-6">
                            <button onClick={() => setEditTab('account')} className={`flex-1 py-2 text-xs font-black uppercase tracking-widest rounded-xl transition-all ${editTab === 'account' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>Account</button>
                            <button onClick={() => setEditTab('personnel')} className={`flex-1 py-2 text-xs font-black uppercase tracking-widest rounded-xl transition-all ${editTab === 'personnel' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>Personnel</button>
                        </div>

                        <form onSubmit={async (e) => {
                            e.preventDefault();
                            if (editTab === 'personnel' && selectedUser.employee) {
                                const nicRegex = /^(\d{9}[Vv]|\d{12})$/;
                                if (!nicRegex.test(selectedUser.employee.national_id)) {
                                    toast.error("Invalid National ID format");
                                    return;
                                }
                            }

                            if (isChangingPassword) {
                                if (newPassword !== confirmNewPassword) {
                                    toast.error("Passwords mismatch"); return;
                                }
                                if (newPassword.length < 6) {
                                    toast.error("Password too weak"); return;
                                }
                            }

                            try {
                                const payload = {
                                    email: selectedUser.email,
                                    username: selectedUser.username,
                                    is_active: selectedUser.status === 'active'
                                };
                                if (selectedUser.employee) payload.employee = selectedUser.employee;
                                if (selectedUser.role === 'driver' && selectedUser.driver_profile) payload.driver_profile = selectedUser.driver_profile;
                                if (isChangingPassword) payload.password = newPassword;

                                await api.patch(`users/${selectedUser.id}/`, payload);
                                fetchUsers();
                                setActiveAction(null);
                                setIsChangingPassword(false);
                                toast.success("Identity Updated Successfully");
                            } catch(err) {
                                toast.error("Update failed");
                            }
                        }} className="space-y-6">
                            {editTab === 'account' ? (
                                <div className="space-y-4">
                                    <InputField label="Username" value={selectedUser.username || ""} onChange={e => setSelectedUser({...selectedUser, username: e.target.value})} required icon={<BiUser/>} />
                                    <InputField label="Email Address" value={selectedUser.email || ""} onChange={e => setSelectedUser({...selectedUser, email: e.target.value})} required icon={<BiEnvelope/>} />
                                    
                                    <div className="pt-4 border-t border-slate-100">
                                        <div className="flex items-center justify-between mb-4">
                                            <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest">Security Override</h3>
                                            <button type="button" onClick={() => setIsChangingPassword(!isChangingPassword)} className="text-[10px] font-black text-indigo-600 hover:underline uppercase tracking-widest">
                                                {isChangingPassword ? "Cancel Update" : "Force New Password"}
                                            </button>
                                        </div>
                                        {isChangingPassword && (
                                            <div className="grid grid-cols-2 gap-4 animate-fade-in">
                                                <InputField label="New Secret" type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)} required />
                                                <InputField label="Confirm Secret" type="password" value={confirmNewPassword} onChange={e => setConfirmNewPassword(e.target.value)} required />
                                            </div>
                                        )}
                                    </div>
                                </div>
                            ) : (
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                    <div className="sm:col-span-2">
                                        <InputField label="Full Personnel Name" value={selectedUser.employee?.full_name || ""} onChange={e => setSelectedUser({...selectedUser, employee: {...(selectedUser.employee||{}), full_name: e.target.value}})} required />
                                    </div>
                                    <InputField label="National ID" value={selectedUser.employee?.national_id || ""} onChange={e => setSelectedUser({...selectedUser, employee: {...(selectedUser.employee||{}), national_id: e.target.value}})} required />
                                    <InputField label="Primary Contact" value={selectedUser.employee?.contact_number || ""} onChange={e => setSelectedUser({...selectedUser, employee: {...(selectedUser.employee||{}), contact_number: e.target.value}})} required />
                                    <div className="sm:col-span-2">
                                        <InputField label="Primary Residence" value={selectedUser.employee?.address || ""} onChange={e => setSelectedUser({...selectedUser, employee: {...(selectedUser.employee||{}), address: e.target.value}})} required />
                                    </div>
                                    <InputField label="Date of Birth" type="date" value={selectedUser.employee?.date_of_birth || ""} onChange={e => setSelectedUser({...selectedUser, employee: {...(selectedUser.employee||{}), date_of_birth: e.target.value}})} required />
                                    {selectedUser.role === 'driver' && (
                                        <>
                                            <div className="sm:col-span-2 mt-2 pt-4 border-t border-slate-100">
                                                <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest mb-2">Driver Authorization</h3>
                                            </div>
                                            <InputField label="License ID" value={selectedUser.driver_profile?.license_number || ""} onChange={e => setSelectedUser({...selectedUser, driver_profile: {...(selectedUser.driver_profile||{}), license_number: e.target.value}})} required />
                                            <InputField label="License Expiry" type="date" value={selectedUser.driver_profile?.license_expiry_date || ""} onChange={e => setSelectedUser({...selectedUser, driver_profile: {...(selectedUser.driver_profile||{}), license_expiry_date: e.target.value}})} required />
                                            <div>
                                                <label className="block text-[11px] font-bold text-slate-400 mb-1.5 uppercase tracking-widest">Auth Classification</label>
                                                <select value={selectedUser.driver_profile?.license_type || "heavy_vehicle"} onChange={e => setSelectedUser({...selectedUser, driver_profile: {...(selectedUser.driver_profile||{}), license_type: e.target.value}})} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm font-medium outline-none">
                                                    <option value="heavy_vehicle">Heavy Transport (HT)</option>
                                                    <option value="light_vehicle">Light Distribution (LD)</option>
                                                    <option value="trailer">Articulated Trailer</option>
                                                </select>
                                            </div>
                                            <InputField label="Experience (Yrs)" type="number" step="0.5" value={selectedUser.driver_profile?.experience_years || ""} onChange={e => setSelectedUser({...selectedUser, driver_profile: {...(selectedUser.driver_profile||{}), experience_years: e.target.value}})} required />
                                        </>
                                    )}
                                </div>
                            )}

                            <div className="flex justify-end gap-3 pt-4">
                                <button type="button" onClick={() => setActiveAction(null)} className="px-6 py-2.5 text-sm font-bold text-slate-500 hover:bg-slate-50 rounded-xl transition-all">Cancel</button>
                                <button type="submit" className="bg-indigo-600 hover:bg-indigo-700 text-white px-8 py-2.5 rounded-xl shadow-lg shadow-indigo-100 text-sm font-bold transition-all">Synchronize Changes</button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            <ConfirmationModal 
                isOpen={!!deleteTarget}
                title="Revoke Permission"
                message={deleteTarget ? (deleteTarget.boundVehicleId ? `This item is currently bound. Do you want to revoke the binding and delete it?` : `Are you sure you want to permanently revoke access for ${deleteTarget.username}? This process is irreversible.`) : ''}
                confirmText={deleteTarget?.boundVehicleId ? "Revoke Binding & Delete" : "Revoke Access"}
                cancelText="Retain Access"
                onConfirm={async () => {
                    if (deleteTarget) {
                        try {
                            if (deleteTarget.boundVehicleId) {
                                try {
                                    await api.patch(`vehicles/${deleteTarget.boundVehicleId}/`, { assignedDriver: null });
                                } catch (e) {}
                            }
                            await api.delete(`users/${deleteTarget.id}/`);
                            toast.success("Access Revoked");
                            fetchUsers();
                        } catch (err) { toast.error("Revocation failed"); }
                    }
                    setDeleteTarget(null);
                }}
                onCancel={() => setDeleteTarget(null)}
            />
            
            {activeAction === 'CREATE_USER' && <CreateUserPopup onClose={() => { setActiveAction(null); fetchUsers(); }} />}
            {activeAction === 'ASSIGN_ROLES' && <AssignRolesPopup onClose={() => { setActiveAction(null); fetchUsers(); }} />}
        </div>
    );
}

function StatCard({ label, value, icon, color }) {
    const colors = {
        coffee: 'bg-coffee-50 text-coffee-700 border-coffee-100',
        emerald: 'bg-emerald-50 text-emerald-700 border-emerald-100',
        amber: 'bg-amber-50 text-amber-700 border-amber-100',
        blue: 'bg-blue-50 text-blue-700 border-blue-100',
    };
    return (
        <div className={`p-6 rounded-[32px] border ${colors[color]} shadow-sm transition-all hover:shadow-md`}>
            <div className="flex items-center justify-between mb-2">
                <div className="p-2.5 bg-white/60 rounded-2xl text-2xl shadow-inner">{icon}</div>
                <div className="text-3xl font-black tracking-tight">{value}</div>
            </div>
            <p className="text-[10px] font-black uppercase tracking-widest opacity-60">{label}</p>
        </div>
    );
}

function StatusBadge({ status }) {
    const isActive = status !== 'inactive';
    return (
        <div className={`px-4 py-1.5 rounded-full text-[10px] font-black uppercase tracking-widest border flex items-center w-max ${isActive ? 'bg-emerald-50 text-emerald-700 border-emerald-100' : 'bg-rose-50 text-rose-700 border-rose-100'}`}>
            <span className={`w-1.5 h-1.5 rounded-full mr-2.5 ${isActive ? 'bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.3)]' : 'bg-rose-500'}`}></span>
            {isActive ? 'Active' : 'Deactivated'}
        </div>
    );
}

function getRoleStyles(role) {
    switch(role) {
        case 'admin': return 'bg-rose-50 text-rose-700 border-rose-100';
        case 'manager': return 'bg-amber-50 text-amber-700 border-amber-100';
        case 'driver': return 'bg-emerald-50 text-emerald-700 border-emerald-100';
        case 'customer': return 'bg-coffee-50 text-coffee-700 border-coffee-100';
        default: return 'bg-coffee-50/30 text-coffee-600 border-coffee-100/50';
    }
}
