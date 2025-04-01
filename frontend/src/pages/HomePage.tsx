// src/pages/HomePage.tsx
import { Link } from "react-router-dom";

// Import component
import ImageCompareSlider from "@/components/ImageCompareSlider"; // Assumes correct path

// Import images for the homepage features
import imgGhibli from '@/assets/images/anime-ghibli.png';
import imgDragonball from '@/assets/images/anime-dragonball.png';
import imgHannaBarbera from '@/assets/images/cartoon-hannabarbera2.png';
import imgLooneyTunes from '@/assets/images/cartoon-looneytunes.png';

// Import images for the Before/After slider
import imgBefore from '@/assets/images/photo-original.png';
import imgAfter from '@/assets/images/photo-anime-style.png';

const featuredStyles = [
    { name: "Studio Anime Style", src: imgGhibli },
    { name: "Action Anime Style", src: imgDragonball },
    { name: "80s Cartoon Style", src: imgHannaBarbera },
    { name: "Cartoon Style", src: imgLooneyTunes },
];

export default function HomePage() {
    return (
        <div className="text-gray-800 pt-1">
            {/* Header Section */}
            <header className="text-center py-16 md:py-16 px-4">
                {/* ... (header content) ... */}
                <h1 className="text-4xl md:text-5xl font-extrabold text-gray-900 mb-4 leading-tight">
                    Stylize Your Photos Like Never Before
                </h1>
                <p className="text-lg text-gray-600 mb-2 max-w-2xl mx-auto">
                    Instantly transform your photos with unique artistic styles. See the magic yourself!
                </p>
            </header>

            <div className="text-center">
                <Link
                    to="/gallery"
                    className="inline-block px-8 py-3 text-white bg-gray-950 hover:bg-gray-800 rounded-lg text-lg font-semibold shadow hover:shadow-md transition-all duration-200"
                >
                    Choose Your Style
                </Link>
            </div>

            {/* Before/After Slider Section */}
            <section className="px-4 py-10 md:py-20">
                <h2 className="text-3xl font-bold text-center mb-8 text-gray-800">See the Transformation</h2>
                {/* Use the ImageCompareSlider component WITH sizing classes */}
                <ImageCompareSlider
                    // Add className to control max-width and centering
                    className="max-w-5xl mx-auto" // <-- INCREASED SIZE (adjust max-w- as needed)
                    beforeImage={imgBefore}
                    afterImage={imgAfter}
                    altBefore="Original photograph"
                    altAfter="Photograph transformed into Anime style"
                />
            </section>


            {/* Featured Styles Section */}
            <section className="px-6 pb-16 md:pb-20 md:py-16 max-w-5xl mx-auto">
                {/* ... (featured styles content) ... */}
                <h2 className="text-3xl font-bold text-center mb-8 text-gray-800">Popular Styles</h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-6">
                    {featuredStyles.map((style) => (
                        <div
                            key={style.name}
                            className="bg-white rounded-xl overflow-hidden shadow-md hover:shadow-lg transition-shadow duration-300 ease-in-out transform hover:-translate-y-1"
                        >
                            <img
                                src={style.src}
                                alt={`${style.name} example`}
                                className="w-full h-52 object-cover"
                            />
                            <p className="text-center font-medium p-3 text-gray-700">{style.name}</p>
                        </div>
                    ))}
                </div>
            </section>
        </div>
    );
}