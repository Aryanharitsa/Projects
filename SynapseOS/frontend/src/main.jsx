import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";

import "./index.css";
import App from "./App.jsx";
import Landing from "./pages/Landing.jsx";
import Brain from "./pages/Brain.jsx";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<App />}>
          <Route path="/" element={<Landing />} />
          <Route path="/brain" element={<Brain />} />
        </Route>
      </Routes>
    </BrowserRouter>
    <Toaster position="top-right" theme="dark" richColors />
  </StrictMode>
);
