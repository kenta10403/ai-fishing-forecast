import React from 'react';
import { Flame, ThermometerSun, Wind } from 'lucide-react';
import { clsx } from 'clsx';

const mockRankings = [
    { rank: 1, name: '本牧海づり施設', score: 92, trend: true, waterTemp: '16.5℃', wind: '北東 2m/s', tags: ['アジ好調', 'イワシ回遊中'] },
    { rank: 2, name: '大黒海づり施設', score: 85, trend: false, waterTemp: '16.2℃', wind: '北東 3m/s', tags: ['サバ回遊', '夕まずめに期待'] },
    { rank: 3, name: '磯子海づり施設', score: 78, trend: false, waterTemp: '16.8℃', wind: '北 1m/s', tags: ['ウミタナゴ', 'メバル'] },
    { rank: 4, name: '市原市海づり施設', score: 65, trend: false, waterTemp: '15.9℃', wind: '北 4m/s', tags: ['サッパ', '風に注意'] },
];

const LocationRanking: React.FC = () => {
    return (
        <div className="py-4 space-y-6 animate-in fade-in duration-500">
            <div className="text-center space-y-2">
                <h1 className="text-2xl font-black text-slate-800 tracking-tight">どこ行く？ランキング</h1>
                <p className="text-slate-500 text-sm">今日一番熱い施設を探そう！<br />SNSトレンドで確変中の場所もわかる！</p>
            </div>

            <div className="space-y-4">
                {mockRankings.map((loc) => (
                    <div key={loc.name} className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden relative">
                        {loc.rank === 1 && (
                            <div className="absolute top-0 right-0 bg-gradient-to-l from-orange-500 to-amber-500 text-white text-xs font-bold px-3 py-1.5 rounded-bl-xl z-10">
                                ⭐ No.1 おすすめ
                            </div>
                        )}
                        <div className="p-5 flex gap-4">
                            <div className="flex flex-col items-center justify-center min-w-[3rem]">
                                <span className={clsx(
                                    "font-black text-3xl tracking-tighter",
                                    loc.rank === 1 ? "text-orange-500" : loc.rank === 2 ? "text-slate-400" : loc.rank === 3 ? "text-amber-700/60" : "text-slate-300"
                                )}>
                                    {loc.rank}
                                </span>
                                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Rank</span>
                            </div>

                            <div className="flex-1 space-y-2">
                                <div>
                                    <h3 className="text-lg font-bold text-slate-800 flex items-center gap-2">
                                        {loc.name}
                                        {loc.trend && (
                                            <span className="flex items-center gap-1 text-[10px] bg-red-100 text-red-600 px-2 py-0.5 rounded-full font-bold">
                                                <Flame className="w-3 h-3" />
                                                確変中
                                            </span>
                                        )}
                                    </h3>
                                    <div className="flex items-center gap-3 text-xs text-slate-500 mt-1 font-medium">
                                        <span className="flex items-center gap-1"><ThermometerSun className="w-3.5 h-3.5" />{loc.waterTemp}</span>
                                        <span className="flex items-center gap-1"><Wind className="w-3.5 h-3.5" />{loc.wind}</span>
                                    </div>
                                </div>

                                <div className="flex flex-wrap gap-1.5 pt-1">
                                    {loc.tags.map(tag => (
                                        <span key={tag} className="text-[11px] font-bold bg-sky-50 text-sky-600 px-2 py-1 rounded-md">
                                            #{tag}
                                        </span>
                                    ))}
                                </div>
                            </div>

                            <div className="flex flex-col items-center justify-center pl-2 border-l border-slate-100">
                                <span className="text-2xl font-black text-sky-500">{loc.score}</span>
                                <span className="text-[10px] font-bold text-slate-400">SCORE</span>
                            </div>
                        </div>
                        {/* Trend highlight bar */}
                        {loc.trend && <div className="h-1 w-full bg-gradient-to-r from-red-500 to-orange-400" />}
                    </div>
                ))}
            </div>
        </div>
    );
};

export default LocationRanking;
