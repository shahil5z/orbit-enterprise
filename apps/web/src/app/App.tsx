import { lazy, Suspense, type ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Loading } from "../components/ui";
import { FilterProvider } from "../hooks/useFilters";
import { ReferenceProvider } from "../hooks/useReference";
import { Layout } from "./Layout";
import { ErrorBoundary } from "./ErrorBoundary";

const Landing = lazy(() => import("../features/overview/Landing"));
const Overview = lazy(() => import("../features/overview/OverviewPage"));
const Intelligence = lazy(() => import("../features/intelligence/IntelligencePage"));
const Anomalies = lazy(() => import("../features/intelligence/AnomalyExplorer"));
const Forecasts = lazy(() => import("../features/forecasts/ForecastsPage"));
const Risk = lazy(() => import("../features/risk/RiskPage"));
const Operations = lazy(() => import("../features/operations/OperationsPage"));
const Optimization = lazy(() => import("../features/optimization/OptimizationPage"));
const Scenarios = lazy(() => import("../features/scenarios/ScenarioPage"));
const Decisions = lazy(() => import("../features/decisions/DecisionsPage"));
const Quality = lazy(() => import("../features/quality/QualityPage"));
const Models = lazy(() => import("../features/models/ModelsPage"));
const System = lazy(() => import("../features/system/SystemPage"));

const S = ({ children }: { children: ReactNode }) => <ErrorBoundary><Suspense fallback={<Loading rows={6} />}>{children}</Suspense></ErrorBoundary>;

export function App() {
  return (
    <BrowserRouter>
      <FilterProvider>
        <ReferenceProvider>
          <Routes>
            <Route path="/" element={<S><Landing /></S>} />
            <Route element={<Layout />}>
              <Route path="/overview" element={<S><Overview /></S>} />
              <Route path="/intelligence" element={<S><Intelligence /></S>} />
              <Route path="/anomalies" element={<S><Anomalies /></S>} />
              <Route path="/forecasts" element={<S><Forecasts /></S>} />
              <Route path="/risk" element={<S><Risk /></S>} />
              <Route path="/operations" element={<S><Operations /></S>} />
              <Route path="/optimization" element={<S><Optimization /></S>} />
              <Route path="/scenarios" element={<S><Scenarios /></S>} />
              <Route path="/decisions" element={<S><Decisions /></S>} />
              <Route path="/quality" element={<S><Quality /></S>} />
              <Route path="/models" element={<S><Models /></S>} />
              <Route path="/system" element={<S><System /></S>} />
              <Route path="*" element={<Navigate to="/overview" replace />} />
            </Route>
          </Routes>
        </ReferenceProvider>
      </FilterProvider>
    </BrowserRouter>
  );
}
