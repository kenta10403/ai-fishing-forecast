import React from 'react';
import { Outlet, NavLink } from 'react-router-dom';
import { Target, Map, Fish, TrendingUp, CalendarDays } from 'lucide-react';
import { clsx } from 'clsx';

const Layout: React.FC = () => {
    return (
        <div className="flex flex-col min-h-screen bg-slate-50 text-slate-800 font-sans">
            {/* Header */}
            <header className="fixed top-0 w-full bg-white shadow-sm z-50">
                <div className="max-w-2xl mx-auto px-3 py-3 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <Fish className="w-6 h-6 text-sky-500" />
                        <span className="font-bold text-lg text-sky-700">AI釣果予報</span>
                    </div>
                </div>
            </header>

            {/* Main Content Area */}
            <main className="flex-1 w-full max-w-2xl mx-auto pt-16 pb-20 px-2 sm:px-4">
                <Outlet />
            </main>

            {/* Bottom Navigation */}
            <nav className="fixed bottom-0 w-full bg-white border-t border-slate-200 z-50 rounded-t-xl shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.05)] pb-safe">
                <div className="max-w-2xl mx-auto flex justify-around items-center">
                    <NavItem to="/" icon={<CalendarDays className="w-5 h-5" />} label="カレンダー" />
                    <NavItem to="/location" icon={<Map className="w-5 h-5" />} label="場所探し" />
                    <NavItem to="/predict" icon={<Target className="w-5 h-5" />} label="期待値" />
                    <NavItem to="/trend" icon={<TrendingUp className="w-5 h-5" />} label="トレンド" />
                </div>
            </nav>
        </div>
    );
};

interface NavItemProps {
    to: string;
    icon: React.ReactNode;
    label: string;
}

const NavItem: React.FC<NavItemProps> = ({ to, icon, label }) => {
    return (
        <NavLink
            to={to}
            className={({ isActive }) =>
                clsx(
                    "flex flex-col items-center justify-center w-full py-3 gap-1 text-xs font-medium transition-colors",
                    isActive ? "text-sky-600" : "text-slate-400 hover:text-sky-500"
                )
            }
        >
            {icon}
            <span>{label}</span>
        </NavLink>
    );
};

export default Layout;
