import { useState } from "react";
import { Link, NavLink } from "react-router-dom"; // Use NavLink for active styling

export default function Navbar() {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  const toggleMobileMenu = () => {
    setIsMobileMenuOpen(!isMobileMenuOpen);
  };

  // Helper for NavLink active class styling
  const getNavLinkClass = ({ isActive }: { isActive: boolean }): string =>
    `block py-2 px-3 rounded md:p-0 ${isActive
      ? 'text-white bg-indigo-600 md:bg-transparent md:text-indigo-700'
      : 'text-gray-700 hover:bg-gray-100 md:hover:bg-transparent md:hover:text-indigo-600'
    }`;


  return (
    <nav className="bg-amber-50 shadow-sm border-b border-gray-200 px-4 lg:px-6 py-2.5 sticky top-0 z-50">
      <div className="flex flex-wrap justify-between items-center mx-auto max-w-screen-xl">
        {/* Logo */}
        <Link to="/" className="flex items-center">
          <span className="self-center text-xl font-bold whitespace-nowrap text-gray-800">
            FotoStyle
          </span>
          {/* Optional: Add an SVG logo here */}
        </Link>

        {/* Sign In Button & Mobile Menu Toggle */}
        <div className="flex items-center lg:order-2">
          <Link
            to="/signin"
            className="text-gray-800 hover:bg-gray-100 focus:ring-4 focus:ring-gray-300 font-medium rounded-lg text-sm px-4 lg:px-5 py-2 lg:py-2.5 mr-2 focus:outline-none border border-gray-300"
          >
            Sign In
          </Link>
          <button
            onClick={toggleMobileMenu}
            type="button"
            className="inline-flex items-center p-2 ml-1 text-sm text-gray-500 rounded-lg lg:hidden hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-gray-200"
            aria-controls="mobile-menu"
            aria-expanded={isMobileMenuOpen}
          >
            <span className="sr-only">Open main menu</span>
            {/* Hamburger Icon */}
            <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg"><path fillRule="evenodd" d="M3 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 10a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 15a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" clipRule="evenodd"></path></svg>
            {/* Close Icon (Optional - can use same button) */}
            {/* <svg className="hidden w-6 h-6" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg"><path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd"></path></svg> */}
          </button>
        </div>

        {/* Navigation Links */}
        <div
          className={`${isMobileMenuOpen ? "block" : "hidden"} justify-between items-center w-full lg:flex lg:w-auto lg:order-1`}
          id="mobile-menu"
        >
          <ul className="flex flex-col mt-4 font-medium lg:flex-row lg:space-x-8 lg:mt-0">
            <li>
              <NavLink to="/" className={getNavLinkClass} end>
                Home
              </NavLink>
            </li>
            <li>
              <NavLink to="/gallery" className={getNavLinkClass}>
                Gallery
              </NavLink>
            </li>
            <li>
              <NavLink to="/pricing" className={getNavLinkClass}>
                Pricing
              </NavLink>
            </li>
            {/* Add other links like FAQ, Contact etc. if needed */}
          </ul>
        </div>
      </div>
    </nav>
  );
}