import { Routes, Route } from "react-router-dom";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import HomePage from "@/pages/HomePage";
import BrowseStylesPage from "@/pages/BrowseStylesPage";
import SubmitPhotoPage from "@/pages/SubmitPhotoPage";
import PricingPage from "@/pages/PricingPage";
import SignInPage from "@/pages/SignInPage";
import NotFoundPage from "@/pages/NotFoundPage";
import RequestSuccessPage from "@/pages/RequestSuccessPage";

export default function App() {
    return (
        // Apply the Tailwind background class HERE
        <div className="flex flex-col min-h-screen bg-[#fffcf0]">
            <Navbar />
            <main className="flex-grow">
                <Routes>
                    <Route path="/" element={<HomePage />} />
                    <Route path="/gallery" element={<BrowseStylesPage />} />
                    <Route path="/submit/:styleName" element={<SubmitPhotoPage />} />
                    <Route path="/request-success" element={<RequestSuccessPage />} />
                    <Route path="/pricing" element={<PricingPage />} />
                    <Route path="/signin" element={<SignInPage />} />
                    <Route path="*" element={<NotFoundPage />} />
                </Routes>
            </main>
            <Footer />
        </div>
    );
}