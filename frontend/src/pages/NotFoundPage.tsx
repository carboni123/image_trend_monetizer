import { Link } from 'react-router-dom';

export default function NotFoundPage() {
    return (
        <div className="flex items-center justify-center flex-grow py-12 px-4">
            <div className="max-w-md w-full bg-white shadow-lg rounded-lg p-8 text-center">
                <h2 className="text-2xl font-semibold text-gray-700 mb-2">
                    404 - Page Not Found
                </h2>
                <p className="text-gray-600 mb-6">
                    Sorry, the page you are looking for does not exist.
                </p>
                <Link
                    to="/"
                    className="inline-block px-6 py-2 text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg text-md font-semibold shadow hover:shadow-md transition-all duration-200"
                >
                    Go Back Home
                </Link>
            </div>
        </div>
    );
}