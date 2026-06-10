import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Admin } from "@/pages/Admin";
import { Cancel } from "@/pages/Cancel";
import { Home } from "@/pages/Home";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/admin" element={<Admin />} />
        <Route path="/cancel/:token" element={<Cancel />} />
      </Routes>
    </BrowserRouter>
  );
}
