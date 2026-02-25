
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from '@/components/Layout';
import FishingCalendar from '@/pages/FishingCalendar';
import PinpointPrediction from '@/pages/PinpointPrediction';
import LocationRanking from '@/pages/LocationRanking';
import SpeciesRanking from '@/pages/SpeciesRanking';
import SeaTrend from '@/pages/SeaTrend';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<FishingCalendar />} />
          <Route path="location" element={<LocationRanking />} />
          <Route path="predict" element={<PinpointPrediction />} />
          <Route path="species" element={<SpeciesRanking />} />
          <Route path="trend" element={<SeaTrend />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
