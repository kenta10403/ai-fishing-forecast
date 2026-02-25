import React from 'react';
import { TrendingUp, Flame, MessageCircle, Share2, BarChart2 } from 'lucide-react';
import { clsx } from 'clsx';

const mockTrends = [
    { id: 1, fish: 'アジ', area: '東京湾一帯', buzz: 98, level: '確変', desc: '各施設で釣果報告急増中！例年の1.5倍のペースです。', tags: ['サビキ', '夕まずめ'] },
    { id: 2, fish: 'シーバス', area: '川崎・横浜エリア', buzz: 85, level: '上昇中', desc: 'バチ抜けパターン開幕。夜間のルアーで釣果報告多数。', tags: ['ルアー', 'バチ抜け'] },
    { id: 3, fish: 'マゴチ', area: 'サーフ全般', buzz: 70, level: '安定', desc: '少しずつ釣果が出始めています。', tags: ['ルアー', 'サーフ'] },
];

const SeaTrend: React.FC = () => {
    return (
        <div className="py-4 space-y-6 animate-in fade-in duration-500">
            <div className="text-center space-y-2">
                <h1 className="text-2xl font-black text-slate-800 tracking-tight flex items-center justify-center gap-2">
                    <TrendingUp className="w-6 h-6 text-sky-500" />
                    今の海のトレンド
                </h1>
                <p className="text-slate-500 text-sm">神奈川県全体で今バズってる魚はこれだ！<br />釣具屋データ × SNS熱量</p>
            </div>

            <div className="space-y-4">
                {mockTrends.map((trend, index) => (
                    <div key={trend.id} className="bg-white p-5 rounded-2xl shadow-sm border border-slate-100 flex flex-col gap-3 relative overflow-hidden">
                        {index === 0 && (
                            <div className="absolute top-0 right-0 bg-red-500 text-white text-[10px] font-bold px-3 py-1 rounded-bl-xl z-10 flex items-center gap-1 shadow-sm">
                                <Flame className="w-3 h-3" />
                                爆発中
                            </div>
                        )}

                        <div className="flex justify-between items-start">
                            <div>
                                <h3 className="text-xl font-bold text-slate-800 flex items-center gap-2">
                                    #{trend.fish}
                                    <span className={clsx(
                                        "text-[10px] font-bold px-2 py-0.5 rounded-md",
                                        trend.level === '確変' ? "bg-red-100 text-red-600" : trend.level === '上昇中' ? "bg-orange-100 text-orange-600" : "bg-sky-100 text-sky-600"
                                    )}>
                                        {trend.level}
                                    </span>
                                </h3>
                                <p className="text-xs text-slate-400 font-medium flex items-center gap-1 mt-1">
                                    <BarChart2 className="w-3.5 h-3.5" />
                                    {trend.area}
                                </p>
                            </div>

                            <div className="text-center bg-slate-50 px-3 py-2 rounded-xl border border-slate-100 min-w-[4rem]">
                                <div className="text-xs font-bold text-slate-400 mb-0.5">熱量</div>
                                <div className="text-xl font-black text-sky-600">{trend.buzz}</div>
                            </div>
                        </div>

                        <p className="text-sm text-slate-600 leading-relaxed bg-slate-50/50 p-3 rounded-xl border border-slate-100/50">
                            {trend.desc}
                        </p>

                        <div className="flex flex-wrap gap-2 mt-1">
                            {trend.tags.map(tag => (
                                <span key={tag} className="text-xs font-semibold bg-slate-100 text-slate-500 px-2 py-1 rounded-md">
                                    {tag}
                                </span>
                            ))}
                        </div>

                        <div className="flex border-t border-slate-100 pt-3 mt-1 gap-4">
                            <button className="flex-1 flex items-center justify-center gap-2 text-xs font-bold text-slate-500 hover:text-sky-500 transition-colors py-1">
                                <MessageCircle className="w-4 h-4" />
                                釣果を見る
                            </button>
                            <div className="w-px bg-slate-100" />
                            <button className="flex-1 flex items-center justify-center gap-2 text-xs font-bold text-slate-500 hover:text-sky-500 transition-colors py-1">
                                <Share2 className="w-4 h-4" />
                                シェア
                            </button>
                        </div>

                        {/* Progress bar for buzz level */}
                        <div className="h-1 w-full bg-slate-100 absolute bottom-0 left-0">
                            <div
                                className={clsx(
                                    "h-full",
                                    trend.buzz > 90 ? "bg-red-500" : trend.buzz > 80 ? "bg-orange-400" : "bg-sky-400"
                                )}
                                style={{ width: `${trend.buzz}%` }}
                            />
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default SeaTrend;
