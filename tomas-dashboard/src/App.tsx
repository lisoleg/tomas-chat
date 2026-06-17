import { HashRouter, Routes, Route } from 'react-router-dom';
import Layout from '@/components/layout/Layout';
import Dashboard from '@/pages/Dashboard';
import Chat from '@/pages/Chat';
import Distill from '@/pages/Distill';
import WorldModel from '@/pages/WorldModel';
import TShield from '@/pages/TShield';
import Audit from '@/pages/Audit';
import Memory from '@/pages/Memory';
import Firewall from '@/pages/Firewall';
import Zynq from '@/pages/Zynq';
import Settings from '@/pages/Settings';

export default function App() {
  return (
    <HashRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="/distill" element={<Distill />} />
          <Route path="/world" element={<WorldModel />} />
          <Route path="/tshield" element={<TShield />} />
          <Route path="/audit" element={<Audit />} />
          <Route path="/memory" element={<Memory />} />
          <Route path="/firewall" element={<Firewall />} />
          <Route path="/zynq" element={<Zynq />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </Layout>
    </HashRouter>
  );
}
