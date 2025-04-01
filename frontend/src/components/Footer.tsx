import React from 'react';

const Footer: React.FC = () => {
  const currentYear = new Date().getFullYear();

  return (
    // Use a complementary brown or dark gray. Let's try brand-brown.
    // Adjust text color for contrast. text-beige-light or text-gray-200 might work.
    <footer className="bg-brand-brown text-beige-light py-4 mt-auto w-full"> {/* CHANGED */}
      <div className="container mx-auto px-4">
        <p className="text-center text-sm">
          Copyright © FotoStyle {currentYear}
        </p>
      </div>
    </footer>
  );
};

export default Footer;