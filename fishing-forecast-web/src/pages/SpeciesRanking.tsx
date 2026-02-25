import React, { useState } from 'react';
import { MapPin, Trophy, Fish, Sparkles } from 'lucide-react';

const mockFishRanking = [
    { rank: 1, name: 'アジ', type: 'サビキ', size: '15-20cm', chance: 'HIGH', score: 95 },
    { rank: 2, name: 'イワシ', type: 'サビキ', size: '10-15cm', chance: 'HIGH', score: 88 },
    { rank: 3, name: 'クロダイ', type: '落とし込み', size: '30-40cm', chance: 'MEDIUM', score: 72 },
    { rank: 4, name: 'シーバス', type: 'ルアー', size: '40-60cm', chance: 'LOW', score: 55 },
    { rank: 5, name: 'サバ', type: 'サビキ', size: '20-25cm', chance: 'LOW', score: 45 },
];

const getChanceColor = (chance: string) => {
    switch (chance) {
        case 'HIGH': return 'bg-orange-100 text-orange-700 border-orange-200';
        case 'MEDIUM': return 'bg-sky-100 text-sky-700 border-sky-200';
        case 'LOW': return 'bg-slate-100 text-slate-500 border-slate-200';
        default: return 'bg-slate-100 text-slate-500 border-slate-200';
    }
};

const SpeciesRanking: React.FC = () => {
    const [selectedLocation, setSelectedLocation] = useState('honmoku');

    return (
        <div className="py-4 space-y-6 animate-in fade-in duration-500">
            <div className="text-center space-y-2">
                <h1 className="text-2xl font-black text-slate-800 tracking-tight">何釣る？ランキング</h1>
                <p className="text-slate-500 text-sm">行く施設で今日一番釣れそうな魚は？</p>
            </div>

            <div className="space-y-4">
                {/* Location Selector */}
                <div className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100">
                    <label className="text-sm font-semibold text-slate-700 flex items-center gap-1.5 mb-2">
                        <MapPin className="w-4 h-4 text-sky-500" />
                        対象の施設
                    </label>
                    <select
                        value={selectedLocation}
                        onChange={(e) => setSelectedLocation(e.target.value)}
                        className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-slate-700 focus:outline-none focus:ring-2 focus:ring-sky-500/50 appearance-none font-bold"
                    >
                        <option value="honmoku">本牧海づり施設</option>
                        <option value="daikoku">大黒海づり施設</option>
                        <option value="isogo">磯子海づり施設</option>
                        <option value="ichihara">市原市海づり施設</option>
                    </select>
                </div>

                {/* Ranking List */}
                <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden divide-y divide-slate-100">
                    {mockFishRanking.map((fish) => (
                        <div key={fish.name} className="p-4 flex items-center gap-4 hover:bg-slate-50 transition-colors">
                            <div className="flex flex-col items-center justify-center min-w-[2.5rem]">
                                {fish.rank === 1 ? (
                                    <Trophy className="w-8 h-8 text-yellow-500" />
                                ) : fish.rank === 2 ? (
                                    <Trophy className="w-7 h-7 text-slate-300" />
                                ) : fish.rank === 3 ? (
                                    <Trophy className="w-6 h-6 text-amber-700/60" />
                                ) : (
                                    <span className="font-bold text-slate-300 text-xl">{fish.rank}</span>
                                )}
                            </div>

                            <div className="flex-1">
                                <div className="flex items-center gap-2">
                                    <h3 className="text-lg font-bold text-slate-800">{fish.name}</h3>
                                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${getChanceColor(fish.chance)}`}>
                                        {fish.chance === 'HIGH' ? '大チャンス' : fish.chance === 'MEDIUM' ? '狙える' : '難しい'}
                                    </span>
                                </div>
                                <div className="flex items-center gap-3 text-xs text-slate-500 mt-1 font-medium">
                                    <span className="flex items-center gap-1"><Fish className="w-3.5 h-3.5" />{fish.type}</span>
                                    <span className="flex items-center gap-1"><Sparkles className="w-3.5 h-3.5" />目安: {fish.size}</span>
                                </div>
                            </div>

                            <div className="text-right">
                                <div className="text-xl font-black text-sky-500">{fish.score}</div>
                                <div className="text-[9px] font-bold text-slate-400">SCORE</div>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
};

export default SpeciesRanking;
