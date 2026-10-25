import { useState } from 'react';
import { TrendingUp, Play, Calendar, AlertOctagon, Info, CheckCircle2 } from 'lucide-react';
import { 
  ResponsiveContainer, 
  LineChart, 
  Line, 
  XAxis, 
  YAxis, 
  Tooltip, 
  CartesianGrid, 
  Legend 
} from 'recharts';
import type { Examination, ForecastRecord } from '../types/medtwin';

interface TimelineForecastingPanelProps {
  examinations: Examination[];
  forecastRecords: ForecastRecord[];
  onRunForecast: (metric: string, horizonDays: number) => void;
  loadingForecast: boolean;
}

export const TimelineForecastingPanel: React.FC<TimelineForecastingPanelProps> = ({
  examinations,
  forecastRecords,
  onRunForecast,
  loadingForecast,
}) => {
  const [selectedMetric, setSelectedMetric] = useState<string>('JOINT_SPACE_WIDTH_MM');
  const [selectedHorizon, setSelectedHorizon] = useState<number>(90);

  const latestForecast = forecastRecords.find(
    (f) => f.target_metric === selectedMetric && f.horizon_days === selectedHorizon
  );

  // Synthesize chart data combining historical points and forecast points
  const generateChartData = () => {
    // 3 historical points for CASE-MT-2026-081
    const baseData = [
      { date: '2025-10-15', day: 0, observed: 2.45, persistence: null, linear: null, modelForecast: null },
      { date: '2026-01-10', day: 87, observed: 2.38, persistence: null, linear: null, modelForecast: null },
      { date: '2026-04-20', day: 187, observed: 2.29, persistence: 2.29, linear: 2.29, modelForecast: 2.29 },
    ];

    if (latestForecast && latestForecast.status === 'COMPLETED') {
      const forecastDay = 187 + latestForecast.horizon_days;
      baseData.push({
        date: `+${latestForecast.horizon_days}d`,
        day: forecastDay,
        observed: null as unknown as number,
        persistence: latestForecast.baseline_persistence_value ?? 2.29,
        linear: latestForecast.baseline_linear_value ?? 2.21,
        modelForecast: latestForecast.forecast_value ?? 2.24,
      });
    }

    return baseData;
  };

  const chartData = generateChartData();

  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 mb-6 shadow-xl">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-b border-slate-800 pb-4 mb-5">
        <div>
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
              <TrendingUp size={18} />
            </div>
            <h3 className="text-sm font-bold text-white">Longitudinal Timeline & Disease Forecasting (Eqs. 13–14)</h3>
            <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-950 text-emerald-300 border border-emerald-800">
              IEEE Section VI-E
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Tracks dated historical examinations. Enforces eligibility rule (≥ 3 observations); single exam never yields progression.
          </p>
        </div>

        <button
          type="button"
          disabled={loadingForecast}
          onClick={() => onRunForecast(selectedMetric, selectedHorizon)}
          className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow-md shadow-emerald-600/20 transition-all disabled:opacity-50"
        >
          <Play size={13} />
          <span>{loadingForecast ? 'Computing...' : 'Evaluate Forecast'}</span>
        </button>
      </div>

      {/* Target Metric & Horizon Selector */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
        <div>
          <label className="text-xs text-slate-400 mb-1 block">Numeric Target Metric</label>
          <select
            value={selectedMetric}
            onChange={(e) => setSelectedMetric(e.target.value)}
            className="w-full bg-slate-950 text-white font-semibold text-xs rounded-xl border border-slate-800 p-2.5 focus:outline-none focus:border-emerald-500"
          >
            <option value="JOINT_SPACE_WIDTH_MM">Joint Space Width (mm)</option>
            <option value="RADIAL_INCLINATION_DEG">Radial Inclination (deg)</option>
            <option value="QTC_INTERVAL_MS">QTc Interval (ms)</option>
          </select>
        </div>

        <div>
          <label className="text-xs text-slate-400 mb-1 block">Prediction Horizon (H)</label>
          <div className="grid grid-cols-3 gap-1.5">
            {[30, 90, 180].map((h) => (
              <button
                key={h}
                type="button"
                onClick={() => setSelectedHorizon(h)}
                className={`py-2 rounded-xl text-xs font-semibold transition-all ${
                  selectedHorizon === h
                    ? 'bg-emerald-600 text-white'
                    : 'bg-slate-950 text-slate-400 border border-slate-800 hover:bg-slate-800'
                }`}
              >
                {h} Days
              </button>
            ))}
          </div>
        </div>

        <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 text-xs flex flex-col justify-between">
          <span className="text-slate-400">Dated Historical Observations</span>
          <div className="text-sm font-bold text-white mt-1 flex items-center gap-1.5">
            <Calendar size={14} className="text-cyan-400" />
            <span>{examinations.length} Dated Examinations</span>
          </div>
        </div>

        <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 text-xs flex flex-col justify-between">
          <span className="text-slate-400">Forecasting Eligibility</span>
          <div className="text-sm font-bold text-white mt-1 flex items-center gap-1.5">
            {examinations.length >= 3 ? (
              <span className="text-emerald-400 flex items-center gap-1">
                <CheckCircle2 size={14} /> ELIGIBLE (L ≥ 3)
              </span>
            ) : (
              <span className="text-amber-400 flex items-center gap-1">
                <AlertOctagon size={14} /> NOT ELIGIBLE (L &lt; 3)
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Recharts Timeline Visualizer */}
      <div className="h-64 rounded-xl bg-slate-950 border border-slate-800 p-3 mb-5">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="date" stroke="#64748b" tick={{ fontSize: 11 }} />
            <YAxis stroke="#64748b" tick={{ fontSize: 11 }} domain={['dataMin - 0.2', 'dataMax + 0.2']} unit=" mm" />
            <Tooltip
              contentStyle={{ backgroundColor: '#020617', borderColor: '#334155', fontSize: '11px' }}
            />
            <Legend wrapperStyle={{ fontSize: '11px', paddingTop: '8px' }} />
            <Line 
              name="Historical Observed (mm)" 
              type="monotone" 
              dataKey="observed" 
              stroke="#38bdf8" 
              strokeWidth={2.5} 
              dot={{ r: 4, fill: '#38bdf8' }}
            />
            <Line 
              name="Last-Value Persistence" 
              type="monotone" 
              dataKey="persistence" 
              stroke="#94a3b8" 
              strokeDasharray="4 4" 
              strokeWidth={1.5}
            />
            <Line 
              name="Linear Progression Baseline" 
              type="monotone" 
              dataKey="linear" 
              stroke="#f59e0b" 
              strokeDasharray="3 3" 
              strokeWidth={1.5}
            />
            <Line 
              name={`Proposed Forecast (+${selectedHorizon}d)`} 
              type="monotone" 
              dataKey="modelForecast" 
              stroke="#10b981" 
              strokeWidth={2.5} 
              dot={{ r: 5, fill: '#10b981' }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Forecast Estimates & Comparative Baselines */}
      {latestForecast && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs mb-4">
          <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
            <span className="text-slate-400">Proposed Forecast Value</span>
            <div className="text-lg font-bold text-emerald-400 mt-1">
              {latestForecast.forecast_value?.toFixed(2)} {latestForecast.unit}
            </div>
            <span className="text-[10px] text-slate-500">Recurrent Chronological Model</span>
          </div>

          <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
            <span className="text-slate-400">Persistence Baseline</span>
            <div className="text-lg font-bold text-slate-300 mt-1">
              {latestForecast.baseline_persistence_value?.toFixed(2)} {latestForecast.unit}
            </div>
            <span className="text-[10px] text-slate-500">Last-value carry forward</span>
          </div>

          <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
            <span className="text-slate-400">Linear Slope Baseline</span>
            <div className="text-lg font-bold text-amber-400 mt-1">
              {latestForecast.baseline_linear_value?.toFixed(2)} {latestForecast.unit}
            </div>
            <span className="text-[10px] text-slate-500">Ordinary least squares</span>
          </div>

          <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
            <span className="text-slate-400">Evaluation Metric Targets</span>
            <div className="text-xs text-slate-300 mt-1 font-mono">
              <div>MAE: {latestForecast.mae_estimate?.toFixed(3)}</div>
              <div>RMSE: {latestForecast.rmse_estimate?.toFixed(3)}</div>
            </div>
            <span className="text-[10px] text-slate-500">Pending real-world validation</span>
          </div>
        </div>
      )}

      {/* IEEE Caution */}
      <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-300 text-xs flex items-start gap-2.5">
        <Info size={15} className="text-amber-400 shrink-0 mt-0.5" />
        <div>
          <strong>Non-Diagnostic Disclaimer:</strong> Forecasts are experimental simulation estimates.
          They do not constitute clinical prognostic certitude or treatment guides (IEEE Manuscript Section XI).
        </div>
      </div>
    </div>
  );
};
