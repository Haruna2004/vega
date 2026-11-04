import "@fontsource-variable/inter";
import "@fontsource/jetbrains-mono/400.css";
import "maplibre-gl/dist/maplibre-gl.css";
import "./index.css";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Home from "./pages/Home";
import Capture from "./pages/Capture";
import RunLayout from "./pages/RunLayout";
import Review from "./pages/Review";
import MapPage from "./pages/MapPage";
import Defects from "./pages/Defects";
import Orders from "./pages/Orders";
import Ask from "./pages/Ask";

createRoot(document.getElementById("root")!).render(
  <BrowserRouter>
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/capture" element={<Capture />} />
      <Route path="/runs/:runId" element={<RunLayout />}>
        <Route index element={<Navigate to="review" replace />} />
        <Route path="review" element={<Review />} />
        <Route path="map" element={<MapPage />} />
        <Route path="defects" element={<Defects />} />
        <Route path="orders" element={<Orders />} />
        <Route path="ask" element={<Ask />} />
      </Route>
    </Routes>
  </BrowserRouter>
);
