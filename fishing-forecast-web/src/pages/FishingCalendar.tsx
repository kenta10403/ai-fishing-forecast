import React, { useState, useEffect } from 'react';
import { Calendar as CalendarIcon, Sun, CloudRain, Wind, Droplets, Info, X, ChevronLeft, ChevronRight } from 'lucide-react';
import { clsx } from 'clsx';

// Type definitions
type DataType = 'past' | 'forecast' | 'base';

interface DayData {
    date: Date;
    dateStr: string;
    dayNum: number;
    isCurrentMonth: boolean;
    type: DataType;
    score: number;
    weather?: string;
    tide: string;
    trend: 'fire' | 'hot' | 'normal' | 'bad';
    ai_comment: string;
    marine?: {
        temp: number;
        transparency: number;
        wave: number;
        salinity: number;
    };
}

const getWeatherIcon = (weather?: string, size = "w-3 h-3") => {
    if (!weather) return null;
    switch (weather) {
        case 'sunny': return <Sun className={clsx(size, "text-orange-500")} />;
        case 'cloudy': return <CloudRain className={clsx(size, "text-slate-400")} />;
        case 'rain': return <Droplets className={clsx(size, "text-blue-500")} />;
        case 'windy': return <Wind className={clsx(size, "text-teal-500")} />;
        default: return <Sun className={clsx(size, "text-orange-500")} />;
    }
};

const getScoreColor = (score: number, type: DataType) => {
    if (type === 'base') return 'text-slate-400'; // Base expectation is less prominent
    if (score >= 80) return 'text-blue-500';
    if (score >= 60) return 'text-emerald-500';
    if (score >= 40) return 'text-yellow-500';
    if (score >= 20) return 'text-orange-500';
    return 'text-red-500';
};

const FishingCalendar: React.FC = () => {
    const [selectedDay, setSelectedDay] = useState<DayData | null>(null);
    const [currentDate, setCurrentDate] = useState(new Date()); // default to current date
    const [calendarData, setCalendarData] = useState<DayData[]>([]);
    const [isLoading, setIsLoading] = useState(true);

    const daysOfWeek = ['月', '火', '水', '木', '金', '土', '日'];

    useEffect(() => {
        // Fetch generated local data
        const fetchData = async () => {
            try {
                // To support local dev without server configuration, fetch from public folder
                const res = await fetch('/data/frontend_calendar.json');
                const rawData = await res.json();

                const parsedData: DayData[] = rawData.map((d: any) => ({
                    ...d,
                    date: new Date(d.date)
                }));

                // Calculate display dates for current grid
                const firstDayOfMonth = new Date(currentDate.getFullYear(), currentDate.getMonth(), 1);
                // Adjust to previous Monday
                const startOfGrid = new Date(firstDayOfMonth);
                const dayOfWeek = firstDayOfMonth.getDay(); // 0 is Sunday
                const diff = dayOfWeek === 0 ? 6 : dayOfWeek - 1;
                startOfGrid.setDate(firstDayOfMonth.getDate() - diff);

                const days: DayData[] = [];
                for (let i = 0; i < 42; i++) {
                    const d = new Date(startOfGrid);
                    d.setDate(startOfGrid.getDate() + i);

                    // Find matching data from fetched JSON
                    const match = parsedData.find(pd => pd.date.toDateString() === d.toDateString());

                    if (match) {
                        days.push({
                            ...match,
                            dateStr: `${d.getMonth() + 1}/${d.getDate()}`,
                            dayNum: d.getDate(),
                            isCurrentMonth: d.getMonth() === currentDate.getMonth()
                        });
                    } else {
                        // Fallback if date is missing from JSON
                        days.push({
                            date: d,
                            dateStr: `${d.getMonth() + 1}/${d.getDate()}`,
                            dayNum: d.getDate(),
                            isCurrentMonth: d.getMonth() === currentDate.getMonth(),
                            type: 'base',
                            score: 0,
                            tide: 'ー',
                            trend: 'normal',
                            ai_comment: 'データがありません'
                        });
                    }
                }

                setCalendarData(days);
            } catch (error) {
                console.error('Failed to fetch calendar data:', error);
            } finally {
                setIsLoading(false);
            }
        };
        fetchData();
    }, [currentDate]);

    const nextMonth = () => {
        setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 1));
    };

    const prevMonth = () => {
        setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() - 1, 1));
    };

    return (
        <div className="py-2 space-y-4 animate-in fade-in duration-500 relative">
            <div className="text-center space-y-1">
                <h1 className="text-2xl font-black text-slate-800 tracking-tight flex items-center justify-center gap-2">
                    <CalendarIcon className="w-6 h-6 text-sky-500" />
                    爆釣カレンダー
                </h1>
                <p className="text-slate-500 text-xs">天気・潮回りから首都圏の釣果を予測！</p>
            </div>

            {/* Disclaimer */}
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 flex gap-2 items-start text-amber-800 text-xs shadow-sm">
                <Info className="w-5 h-5 shrink-0 mt-0.5" />
                <div className="flex flex-col gap-0.5 leading-relaxed">
                    <p><strong>1週間先まで</strong>は天気・水温予測を加味した高精度スコアを出します。</p>
                    <p><strong>それ以降</strong>は「潮回りと例年の傾向」に基づく基本期待値です。</p>
                </div>
            </div>

            {/* Calendar View */}
            <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
                <div className="p-3 bg-slate-50 border-b border-slate-200 flex justify-between items-center">
                    <button onClick={prevMonth} className="p-1 hover:bg-slate-200 rounded-lg transition-colors">
                        <ChevronLeft className="w-5 h-5 text-slate-600" />
                    </button>
                    <h2 className="font-bold text-slate-700 text-lg">
                        {currentDate.getFullYear()}年 {currentDate.getMonth() + 1}月
                    </h2>
                    <button onClick={nextMonth} className="p-1 hover:bg-slate-200 rounded-lg transition-colors">
                        <ChevronRight className="w-5 h-5 text-slate-600" />
                    </button>
                </div>

                {/* Days Header */}
                <div className="grid grid-cols-7 border-b border-slate-100">
                    {daysOfWeek.map((day, i) => (
                        <div key={day} className={clsx(
                            "text-center py-2 text-[10px] font-bold bg-slate-50",
                            i === 5 ? "text-blue-500" : i === 6 ? "text-red-500" : "text-slate-500"
                        )}>
                            {day}
                        </div>
                    ))}
                </div>

                {/* Grid */}
                <div className="grid grid-cols-7 auto-rows-fr min-h-[30rem] relative">
                    {isLoading ? (
                        <div className="absolute inset-0 flex items-center justify-center bg-white/50 z-10">
                            <div className="animate-spin w-8 h-8 border-4 border-sky-500 border-t-transparent rounded-full" />
                        </div>
                    ) : calendarData.map((day, idx) => {
                        const scorePerc = day.score;
                        const dashArray = 2 * Math.PI * 14;
                        const dashOffset = dashArray * ((100 - scorePerc) / 100);
                        const strokeColor = day.type === 'base' ? '#cbd5e1'
                            : day.score >= 80 ? '#3b82f6'
                                : day.score >= 60 ? '#10b981'
                                    : day.score >= 40 ? '#eab308'
                                        : day.score >= 20 ? '#f97316'
                                            : '#ef4444';

                        return (
                            <div
                                key={idx}
                                onClick={() => setSelectedDay(day)}
                                className={clsx(
                                    "border-b border-r border-slate-100 p-1 sm:p-2 flex flex-col items-center justify-between min-h-[5.5rem] sm:min-h-[7rem] cursor-pointer relative transition-all duration-200",
                                    !day.isCurrentMonth && "opacity-20 pointer-events-none", // Outside current month
                                    day.isCurrentMonth && day.type === 'past' && "bg-slate-100 hover:bg-slate-200 grayscale-[0.2]", // Past: Gray background
                                    day.isCurrentMonth && day.type === 'forecast' && "bg-white hover:bg-sky-50 shadow-[inset_0_0_0_1px_rgba(56,189,248,0.15)]", // Forecast: Bright white, subtle blue highlight
                                    day.isCurrentMonth && day.type === 'base' && "bg-slate-50/80 opacity-60 hover:opacity-100", // Base: semitransparent
                                )}
                            >
                                {day.type === 'past' && day.isCurrentMonth && (
                                    <div className="absolute top-1 left-1 w-1.5 h-1.5 rounded-full bg-slate-400" title="実績データ" />
                                )}

                                <div className="w-full flex justify-between items-start mb-1">
                                    <span className={clsx(
                                        "text-xs sm:text-sm font-black leading-none",
                                        day.date.getDay() === 6 ? "text-blue-500" : day.date.getDay() === 0 ? "text-red-500" : "text-slate-700"
                                    )}>{day.dayNum}</span>
                                    {getWeatherIcon(day.weather, "w-3.5 h-3.5 sm:w-4 sm:h-4")}
                                </div>

                                <div className="flex flex-col items-center justify-center flex-1 w-full relative">
                                    <span className="text-[9px] sm:text-[10px] font-bold text-slate-500 mb-0.5 z-10">{day.tide}</span>

                                    <div className="relative flex items-center justify-center w-10 h-10 sm:w-12 sm:h-12 mt-0.5">
                                        <svg className="absolute inset-0 w-full h-full transform -rotate-90" viewBox="0 0 36 36">
                                            <circle cx="18" cy="18" r="14" fill="none" stroke="#f1f5f9" strokeWidth="3" />
                                            <circle
                                                cx="18" cy="18" r="14"
                                                fill="none"
                                                stroke={day.type === 'base' ? '#cbd5e1' : strokeColor}
                                                strokeWidth="3"
                                                strokeDasharray={dashArray}
                                                strokeDashoffset={dashOffset}
                                                strokeLinecap="round"
                                            />
                                        </svg>
                                        <div className="absolute inset-0 flex items-center justify-center flex-col pt-0.5">
                                            <span className={clsx(
                                                "text-xs sm:text-sm font-black tracking-tighter",
                                                getScoreColor(day.score, day.type)
                                            )}>
                                                {day.score}
                                            </span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        )
                    })}
                </div>

                {/* Legend */}
                <div className="p-3 border-t border-slate-100 flex gap-4 sm:gap-6 text-[10px] sm:text-xs font-bold text-slate-500 justify-center bg-slate-50">
                    <div className="flex items-center gap-1.5"><div className="w-3 h-3 rounded-md bg-slate-100 border border-slate-200" />過去の実績</div>
                    <div className="flex items-center gap-1.5"><div className="w-3 h-3 rounded-md bg-white border border-sky-200 shadow-sm" />1週間予測</div>
                    <div className="flex items-center gap-1.5"><div className="w-3 h-3 rounded-md bg-slate-50 border border-slate-200 opacity-60" />基本期待値</div>
                </div>
            </div>

            {/* Detail Modal Overlay */}
            {selectedDay && (
                <div className="fixed inset-0 z-[100] bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-200"
                    onClick={() => setSelectedDay(null)}>
                    <div className="bg-white rounded-3xl w-full max-w-sm shadow-2xl overflow-hidden"
                        onClick={e => e.stopPropagation()}>
                        {/* Modal Header */}
                        <div className={clsx(
                            "p-5 flex justify-between items-start text-white",
                            selectedDay.type === 'forecast' ? "bg-gradient-to-br from-sky-500 to-blue-600"
                                : selectedDay.type === 'base' ? "bg-gradient-to-br from-amber-500 to-orange-500"
                                    : "bg-gradient-to-br from-slate-500 to-slate-600"
                        )}>
                            <div>
                                <div className="flex items-center gap-2 mb-1">
                                    <span className="bg-white/20 px-2 py-0.5 rounded-full text-[10px] font-bold backdrop-blur-md">
                                        {selectedDay.type === 'forecast' ? '🎯 AI天気予測'
                                            : selectedDay.type === 'base' ? '📅 基本期待値'
                                                : '📝 確定実績'}
                                    </span>
                                    <span className="text-sm font-bold opacity-90">{currentDate.getFullYear()}年 {selectedDay.dateStr}</span>
                                </div>
                                <h3 className="text-2xl font-black flex items-baseline gap-2">
                                    指数 <span className="text-5xl">{selectedDay.score}</span>
                                </h3>
                            </div>
                            <button
                                onClick={() => setSelectedDay(null)}
                                className="p-1 rounded-full bg-white/10 hover:bg-white/20 transition-colors"
                            >
                                <X className="w-5 h-5" />
                            </button>
                        </div>

                        {/* Modal Body */}
                        <div className="p-5 space-y-4">
                            <div className="flex justify-around items-center py-3 bg-slate-50 rounded-2xl border border-slate-100">
                                <div className="text-center w-1/3">
                                    <div className="text-[10px] font-bold text-slate-400 mb-1">天気予報</div>
                                    <div className="flex justify-center text-sm font-bold text-slate-700">
                                        {selectedDay.weather ? getWeatherIcon(selectedDay.weather, "w-6 h-6") : "不明"}
                                    </div>
                                </div>
                                <div className="w-px h-8 bg-slate-200" />
                                <div className="text-center w-1/3">
                                    <div className="text-[10px] font-bold text-slate-400 mb-1">潮回り</div>
                                    <div className="text-sm font-bold text-slate-700">{selectedDay.tide}</div>
                                </div>
                                <div className="w-px h-8 bg-slate-200" />
                                <div className="text-center w-1/3">
                                    <div className="text-[10px] font-bold text-slate-400 mb-1">期待度</div>
                                    <div className="font-bold text-sm">
                                        {selectedDay.score >= 80 ? '🔥 激アツ'
                                            : selectedDay.score >= 60 ? '👍 良さげ'
                                                : selectedDay.score < 30 ? '⚠️ 渋い' : 'ー'}
                                    </div>
                                </div>
                            </div>

                            {selectedDay.marine && (
                                <div className="grid grid-cols-2 gap-2">
                                    <div className="bg-sky-50/50 p-3 rounded-xl border border-sky-100 flex items-center gap-3">
                                        <div className="bg-white p-1.5 rounded-lg shadow-sm"><Droplets className="w-4 h-4 text-sky-500" /></div>
                                        <div>
                                            <div className="text-[10px] text-slate-400 font-bold">推定水温</div>
                                            <div className="text-sm font-black text-slate-700">{selectedDay.marine.temp}℃</div>
                                        </div>
                                    </div>
                                    <div className="bg-blue-50/50 p-3 rounded-xl border border-blue-100 flex items-center gap-3">
                                        <div className="bg-white p-1.5 rounded-lg shadow-sm"><Wind className="w-4 h-4 text-blue-500" /></div>
                                        <div>
                                            <div className="text-[10px] text-slate-400 font-bold">最大波高</div>
                                            <div className="text-sm font-black text-slate-700">{selectedDay.marine.wave}m</div>
                                        </div>
                                    </div>
                                    <div className="bg-teal-50/50 p-3 rounded-xl border border-teal-100 flex items-center gap-3">
                                        <div className="bg-white p-1.5 rounded-lg shadow-sm"><Info className="w-4 h-4 text-teal-500" /></div>
                                        <div>
                                            <div className="text-[10px] text-slate-400 font-bold">透明度</div>
                                            <div className="text-sm font-black text-slate-700">{selectedDay.marine.transparency}m</div>
                                        </div>
                                    </div>
                                    <div className="bg-indigo-50/50 p-3 rounded-xl border border-indigo-100 flex items-center gap-3">
                                        <div className="bg-white p-1.5 rounded-lg shadow-sm"><Droplets className="w-4 h-4 text-indigo-500" /></div>
                                        <div>
                                            <div className="text-[10px] text-slate-400 font-bold">塩分濃度</div>
                                            <div className="text-sm font-black text-slate-700">{selectedDay.marine.salinity}</div>
                                        </div>
                                    </div>
                                </div>
                            )}

                            <div>
                                <h4 className="text-xs font-bold text-slate-500 mb-2 tracking-wider">AIの分析コメント</h4>
                                <div className="text-sm text-slate-700 leading-relaxed bg-slate-900 text-white p-4 rounded-2xl shadow-lg relative overflow-hidden">
                                    <div className="absolute top-0 right-0 p-2 opacity-10"><Info className="w-12 h-12" /></div>
                                    <span className="relative z-10">{selectedDay.ai_comment}</span>
                                </div>
                            </div>

                            <div className="pt-2">
                                <button
                                    className="w-full bg-slate-900 text-white font-bold py-3.5 rounded-xl hover:bg-slate-800 transition-colors active:scale-95"
                                    onClick={() => setSelectedDay(null)}
                                >
                                    閉じる
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default FishingCalendar;
