import { Link, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import About from "./pages/About";
import Analytics from "./pages/Analytics";
import AssociationDetail from "./pages/AssociationDetail";
import BiomarkerDetail from "./pages/BiomarkerDetail";
import BiomarkerExplorer from "./pages/BiomarkerExplorer";
import { CancerDetail, CancerList } from "./pages/Cancers";
import Dashboard from "./pages/Dashboard";
import { EntityBrowser, GeneDetail, PathwayDetail, ProteinDetail, VariantDetail } from "./pages/Entities";
import Gaps from "./pages/Gaps";
import ImportPage from "./pages/ImportPage";
import Methodology from "./pages/Methodology";
import Prevalence from "./pages/Prevalence";
import Publications from "./pages/Publications";
import Validation from "./pages/Validation";

function NotFound() {
  return (
    <div className="py-16 text-center">
      <h1 className="text-xl font-semibold text-navy-900">Page not found</h1>
      <Link to="/" className="mt-2 inline-block text-teal-brand hover:underline">Back to dashboard</Link>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="biomarkers" element={<BiomarkerExplorer />} />
        <Route path="biomarkers/:id" element={<BiomarkerDetail />} />
        <Route path="cancers" element={<CancerList />} />
        <Route path="cancers/:id" element={<CancerDetail />} />
        <Route path="associations/:id" element={<AssociationDetail />} />
        <Route path="entities" element={<EntityBrowser />} />
        <Route path="genes/:id" element={<GeneDetail />} />
        <Route path="proteins/:id" element={<ProteinDetail />} />
        <Route path="pathways/:id" element={<PathwayDetail />} />
        <Route path="variants/:id" element={<VariantDetail />} />
        <Route path="publications" element={<Publications />} />
        <Route path="gaps" element={<Gaps />} />
        <Route path="prevalence" element={<Prevalence />} />
        <Route path="validation" element={<Validation />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="methodology" element={<Methodology />} />
        <Route path="import" element={<ImportPage />} />
        <Route path="about" element={<About />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
