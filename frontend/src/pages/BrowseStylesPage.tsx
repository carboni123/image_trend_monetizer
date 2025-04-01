import { useNavigate } from 'react-router-dom';

// Import style images
import imgGhibli from '@/assets/images/anime-ghibli.png';
import imgDragonball from '@/assets/images/anime-dragonball.png';
import imgHannaBarbera from '@/assets/images/cartoon-hannabarbera2.png';
import imgLooneyTunes from '@/assets/images/cartoon-looneytunes.png';

const styles = [
    { name: "Anime Studio", image: imgGhibli, slug: "anime-studio" },
    { name: "Anime", image: imgDragonball, slug: "anime-classic" },
    { name: "Cartoon", image: imgHannaBarbera, slug: "cartoon-classic" },
    { name: "Cartoon 90s", image: imgLooneyTunes, slug: "cartoon-90s" },
];

const animeImageModules = import.meta.glob<{ default: string }>('@/assets/images/gallery/*.png', { eager: true });
const animeImages = Object.values(animeImageModules).map((module) => module.default);

export default function BrowseStylesPage() {
    const navigate = useNavigate();

    const handleStyleClick = (slug: string) => {
        navigate(`/submit/${slug}`);
    };

    // const handleGenericSubmitClick = () => {
    //      if (styles.length > 0) {
    //         navigate(`/submit/${styles[0].slug}`);
    //      }
    //     console.log("Generic submit clicked - implement desired behavior");
    // };

    return (
        // REMOVED background class. Inherits bg-beige-main from App.
        <div className="min-h-screen py-8"> {/* CHANGED */}
            <div className="p-4 max-w-4xl mx-auto">
                <h1 className="text-3xl font-bold text-center mb-8 text-gray-800">Browse & Select Your Style</h1>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 mb-12">
                    {styles.map((style) => (
                        <div
                            key={style.slug}
                            // Added bg-white to make cards stand out
                            className="bg-white cursor-pointer transition-all duration-300 border border-gray-200 rounded-2xl overflow-hidden hover:shadow-xl hover:scale-105 group" // CHANGED
                            onClick={() => handleStyleClick(style.slug)}
                        >
                            <img
                                src={style.image}
                                alt={style.name}
                                className="w-full h-60 object-cover"
                            />
                            <p className="text-center p-3 font-semibold text-gray-700 group-hover:text-indigo-600">
                                {style.name}
                            </p>
                        </div>
                    ))}
                </div>

                {/* Example Gallery Section - Let's give the image containers a white bg too */}
                <div className="text-center mb-10">
                    <h2 className="text-2xl font-semibold mb-4 text-gray-800">Example Gallery (Anime)</h2>
                    <div className="flex overflow-x-auto space-x-4 pb-4 justify-center">
                         {animeImages.length > 0 ? animeImages.map((src, idx) => (
                            <div key={idx} className="flex-shrink-0 w-52 md:w-64 rounded-xl overflow-hidden shadow-md bg-white"> {/* CHANGED */}
                                <img
                                    src={src}
                                    alt={`Anime style example ${idx + 1}`}
                                    className="w-full h-64 object-cover"
                                />
                            </div>
                         )) : <p className="text-gray-500">Gallery images not found.</p>}
                    </div>
                    {/* <button
                        onClick={handleGenericSubmitClick}
                        className="mt-6 px-6 py-3 text-white bg-indigo-600 rounded-lg text-lg hover:bg-indigo-700 transition shadow hover:shadow-lg"
                    >
                        Submit A Photo (Select Style Above)
                    </button> */}
                </div>
            </div>
        </div>
    );
}