import React, { useState } from 'react';
import { Calendar, MapPin, Fish, Search, Activity } from 'lucide-react';


const PinpointPrediction: React.FC = () => {
    const [isPredicting, setIsPredicting] = useState(false);
    const [score, setScore] = useState<number | null>(null);

    const handlePredict = (e: React.FormEvent) => {
        e.preventDefault();
        setIsPredicting(true);
        setScore(null);
        // Simulate API call
        setTimeout(() => {
            setIsPredicting(false);
            setScore(85); // Mock score
        }, 1000);
    };

    return (
        <div className="py-4 space-y-6 animate-in fade-in duration-500">
            <div className="text-center space-y-2">
                <h1 className="text-2xl font-black text-slate-800 tracking-tight">期待値検索</h1>
                <p className="text-slate-500 text-sm">いつ・どこで・何を釣る？<br />釣果の確率をAIがズバリ予測！</p>
            </div>

            <form onSubmit={handlePredict} className="bg-white p-5 rounded-2xl shadow-sm border border-slate-100 space-y-4">
                {/* Date Select */}
                <div className="space-y-1.5">
                    <label className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
                        <Calendar className="w-4 h-4 text-sky-500" />
                        行く日
                    </label>
                    <input
                        type="date"
                        className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-slate-700 focus:outline-none focus:ring-2 focus:ring-sky-500/50 focus:border-sky-500 transition-all"
                        defaultValue={new Date().toISOString().split('T')[0]}
                        required
                    />
                </div>

                {/* Location Select */}
                <div className="space-y-1.5">
                    <label className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
                        <MapPin className="w-4 h-4 text-sky-500" />
                        場所
                    </label>
                    <select className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-slate-700 focus:outline-none focus:ring-2 focus:ring-sky-500/50 appearance-none" required>
                        <option value="">施設を選んでね</option>
                        <option value="honmoku">本牧海づり施設</option>
                        <option value="daikoku">大黒海づり施設</option>
                        <option value="isogo">磯子海づり施設</option>
                        <option value="ichihara">市原市海づり施設</option>
                    </select>
                </div>

                {/* Species Select */}
                <div className="space-y-1.5">
                    <label className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
                        <Fish className="w-4 h-4 text-sky-500" />
                        ターゲット
                    </label>
                    <select className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-slate-700 focus:outline-none focus:ring-2 focus:ring-sky-500/50 appearance-none" required>
                        <option value="">魚種を選んでね</option>
                        <option value="aji">アジ</option>
                        <option value="saba">サバ</option>
                        <option value="iwashi">イワシ</option>
                        <option value="kurodai">クロダイ</option>
                        <option value="suzuki">スズキ</option>
                    </select>
                </div>

                <button
                    type="submit"
                    disabled={isPredicting}
                    className="w-full mt-2 bg-gradient-to-r from-sky-500 to-blue-600 hover:from-sky-400 hover:to-blue-500 text-white font-bold py-3.5 px-4 rounded-xl shadow-md shadow-blue-500/20 active:scale-[0.98] transition-all flex justify-center items-center gap-2"
                >
                    {isPredicting ? (
                        <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    ) : (
                        <>
                            <Search className="w-5 h-5" />
                            予測する！
                        </>
                    )}
                </button>
            </form>

            {/* Result Section (Mock) */}
            {score !== null && (
                <div className="bg-gradient-to-br from-white to-sky-50 p-6 rounded-2xl shadow-sm border border-sky-100 flex flex-col items-center justify-center space-y-3 animate-in slide-in-from-bottom-4 duration-500">
                    <div className="flex items-center gap-2 text-sky-600 font-bold">
                        <Activity className="w-5 h-5" />
                        ボウズ逃れ指標
                    </div>
                    <div className="relative flex items-center justify-center w-32 h-32">
                        <svg className="w-full h-full transform -rotate-90">
                            <circle cx="64" cy="64" r="56" className="stroke-slate-100" strokeWidth="12" fill="none" />
                            <circle
                                cx="64" cy="64" r="56"
                                className="stroke-orange-500"
                                strokeWidth="12"
                                fill="none"
                                strokeDasharray="351.85"
                                strokeDashoffset={351.85 - (351.85 * score) / 100}
                                strokeLinecap="round"
                            />
                        </svg>
                        <div className="absolute flex flex-col items-center justify-center">
                            <span className="text-4xl font-black text-slate-800 tracking-tighter">{score}</span>
                            <span className="text-xs font-bold text-slate-400 -mt-1">%</span>
                        </div>
                    </div>
                    <div className="text-center pt-2">
                        <p className="text-orange-600 font-bold text-lg">大チャンス！🎣</p>
                        <p className="text-slate-500 text-sm mt-1">潮回りが良く、適水温に近いです。回遊が期待できます。</p>
                    </div>
                </div>
            )}
        </div>
    );
};

export default PinpointPrediction;
