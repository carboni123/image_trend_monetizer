// src/pages/RequestSuccessPage.tsx
import { Link, useLocation } from 'react-router-dom';

// Simple Checkmark SVG Icon
const CheckIcon = () => (
    <svg
        className="w-16 h-16 text-green-500 mx-auto mb-4" // Increased size and centered
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
        xmlns="http://www.w3.org/2000/svg"
    >
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7"></path>
    </svg>
);

interface LocationState {
    requestId?: string;
    email?: string;
}

export default function RequestSuccessPage() {
    const location = useLocation();
    const state = location.state as LocationState || {};
    const { requestId, email } = state;
    return (
        // Center content vertically and horizontally
        <div className="flex justify-center items-center md:py-20">
            {/* Content Card */}
            <div className="bg-white p-8 rounded-xl shadow-lg max-w-md w-full text-center"> {/* Centered text */}
                <CheckIcon /> {/* Display the checkmark */}

                <h1 className="text-2xl md:text-3xl font-bold text-gray-800 mb-3">
                    Request Submitted Successfully!
                </h1>

                <p className="text-gray-600 mb-4">
                    Thank you! You'll receive an email with your stylized picture within the next 24 hours. Please check your inbox (and spam folder, just in case).
                </p>
                
                {requestId && (
                    <div className="bg-gray-50 p-4 rounded-lg mb-6">
                        <p className="text-sm text-gray-500 mb-1">Your request ID:</p>
                        <p className="font-mono text-gray-800 font-medium">{requestId}</p>
                        {email && (
                            <p className="text-sm text-gray-500 mt-2">
                                Results will be sent to: <span className="font-medium">{email}</span>
                            </p>
                        )}
                    </div>
                )}

                {/* Links for next actions */}
                <div className="flex flex-col sm:flex-row justify-center gap-4"> {/* Stack on small screens, row on larger */}
                    <Link
                        to="/gallery" // Link to your gallery page
                        className="inline-block px-6 py-2.5 bg-gray-950 text-white font-semibold text-sm leading-tight uppercase rounded-lg shadow-md hover:bg-gray-800 hover:shadow-lg focus:bg-gray-800 focus:shadow-lg focus:outline-none focus:ring-0 active:bg-gray-800 active:shadow-lg transition duration-150 ease-in-out w-full sm:w-auto"
                    >
                        Explore Styles
                    </Link>
                    <Link
                        to="/" // Link to your homepage
                        className="inline-block px-6 py-2.5 bg-gray-200 text-gray-700 font-semibold text-sm leading-tight uppercase rounded-lg shadow-md hover:bg-gray-300 hover:shadow-lg focus:bg-gray-300 focus:shadow-lg focus:outline-none focus:ring-0 active:bg-gray-400 active:shadow-lg transition duration-150 ease-in-out w-full sm:w-auto"
                    >
                        Back to Home
                    </Link>
                </div>
            </div>
        </div>
    );
}
