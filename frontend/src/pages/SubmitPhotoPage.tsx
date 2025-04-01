// src/pages/SubmitPhotoPage.tsx
import React, { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import axios from "axios";

const getStyleDisplayName = (slug: string | undefined): string => {
    if (!slug) return "Selected Style";
    return slug
        .split('-')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
};

export default function SubmitPhotoPage() {
    const { styleName: styleSlug } = useParams<{ styleName: string }>();
    const styleDisplayName = getStyleDisplayName(styleSlug);
    const navigate = useNavigate();

    const [email, setEmail] = useState('');
    const [photoFile, setPhotoFile] = useState<File | null>(null);
    const [receiptFile, setReceiptFile] = useState<File | null>(null);
    const [requestMessage, setRequestMessage] = useState('');
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [submitStatus, setSubmitStatus] = useState('');

    const handlePhotoChange = (event: React.ChangeEvent<HTMLInputElement>) => {
        if (event.target.files && event.target.files[0]) {
            setPhotoFile(event.target.files[0]);
        } else {
            setPhotoFile(null);
        }
    };

    const handleReceiptChange = (event: React.ChangeEvent<HTMLInputElement>) => {
         if (event.target.files && event.target.files[0]) {
            setReceiptFile(event.target.files[0]);
        } else {
            setReceiptFile(null);
        }
    };

    const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        setSubmitStatus('');
        if (!photoFile || !receiptFile || !email || !styleSlug) {
            setSubmitStatus('Please fill in all required fields (*).');
            return;
        }
        setIsSubmitting(true);
        
        // Create FormData object for file upload
        const formData = new FormData();
        formData.append('email', email);
        formData.append('description', `Style: ${styleDisplayName}. ${requestMessage}`);
        formData.append('image', photoFile);
        formData.append('payment_proof', receiptFile);
        
        try {
            // Send request to backend
            const response = await axios.post('/api/submit', formData, {
                headers: {
                    'Content-Type': 'multipart/form-data'
                }
            });
            
            console.log("Submission successful:", response.data);
            
            // Navigate to success page with request ID
            navigate('/request-success', { 
                state: { 
                    requestId: response.data.request_id,
                    email: email
                } 
            });
        } catch (error) {
            console.error("Submission error:", error);
            setSubmitStatus('Submission failed. Please check your details or try again later.');
            setIsSubmitting(false);
        }
    };

    return (
        <div className="min-h-screen p-6 flex justify-center items-start pt-10">
          <div className="max-w-xl w-full">
            <h1 className="text-2xl md:text-3xl font-bold text-center mb-2 text-gray-800">Submit Your Photo</h1>
            <p className="text-center text-gray-600 mb-6">
                You've selected the <span className="font-semibold text-indigo-700">{styleDisplayName}</span> style.
            </p>

            <form onSubmit={handleSubmit} className="bg-white p-6 md:p-8 rounded-xl shadow-lg space-y-5">
                 <div>
                    <label htmlFor="photo" className="block font-medium mb-1 text-gray-700">
                        Upload your photo *
                    </label>
                    <input type="file" id="photo" required accept="image/jpeg, image/png, image/webp" onChange={handlePhotoChange} className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100"/>
                    {photoFile && <span className="text-xs text-gray-500 mt-1 block">Selected: {photoFile.name}</span>}
                 </div>

                 <div>
                    <label htmlFor="receipt" className="block font-medium mb-1 text-gray-700">
                        Upload proof of purchase *
                    </label>
                    <input type="file" id="receipt" required accept="image/jpeg, image/png, image/webp, application/pdf" onChange={handleReceiptChange} className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100"/>
                    {receiptFile && <span className="text-xs text-gray-500 mt-1 block">Selected: {receiptFile.name}</span>}
                 </div>

                 <div>
                    <label htmlFor="email" className="block font-medium mb-1 text-gray-700">
                        Your email address *
                    </label>
                    <input type="email" id="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-indigo-500 focus:border-indigo-500"/>
                 </div>

                 <div>
                    <label htmlFor="requestMessage" className="block font-medium mb-1 text-gray-700">
                        Optional Request Message
                    </label>
                    <textarea
                        id="requestMessage"
                        value={requestMessage}
                        onChange={(e) => setRequestMessage(e.target.value)}
                        placeholder="Any specific instructions or details? (e.g., 'Focus on the character on the left', 'Keep the background simple')"
                        rows={4}
                        className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-indigo-500 focus:border-indigo-500"
                    />
                 </div>

                 {submitStatus && (
                    <p className={`text-sm text-center ${submitStatus.includes('failed') ? 'text-red-600' : 'text-green-600'}`}>
                        {submitStatus}
                    </p>
                 )}

                 <button type="submit" disabled={isSubmitting} className={`w-full bg-indigo-600 hover:bg-indigo-700 text-white text-lg py-2.5 px-4 rounded-md transition duration-200 ease-in-out ${isSubmitting ? 'opacity-50 cursor-not-allowed' : ''}`}>
                    {isSubmitting ? 'Submitting...' : 'Submit Photo'}
                 </button>
            </form>
          </div>
        </div>
    );
}
