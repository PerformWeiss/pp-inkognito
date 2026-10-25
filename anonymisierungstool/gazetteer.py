"""Eingebaute Ortsliste: Länder, Regionen und größere Städte (deutsche, englische und ukrainische/russische Schreibweisen).

Ergänzbar durch das lokale Wörterbuch. Mehrdeutige Wörter (Essen, Halle, Hof, Jordan, Georgia ...) sind bewusst nicht enthalten.
"""
import re

_COUNTRIES = """
Deutschland, Österreich, Schweiz, Liechtenstein, Luxemburg, Belgien, Niederlande, Frankreich, Italien, Spanien, Portugal,
Griechenland, Polen, Tschechien, Slowakei, Ungarn, Rumänien, Bulgarien, Kroatien, Slowenien, Serbien, Bosnien, Herzegowina,
Montenegro, Nordmazedonien, Mazedonien, Albanien, Kosovo, Moldau, Moldawien, Ukraine, Belarus, Weißrussland, Russland,
Litauen, Lettland, Estland, Finnland, Schweden, Norwegen, Dänemark, Island, Irland, Großbritannien, England, Schottland,
Wales, Türkei, Zypern, Malta, Georgien, Armenien, Aserbaidschan, Kasachstan, Usbekistan, Turkmenistan, Tadschikistan,
Kirgisistan, Iran, Irak, Syrien, Libanon, Jordanien, Israel, Palästina, Saudi-Arabien, Jemen, Oman, Katar, Kuwait,
Afghanistan, Pakistan, Indien, Bangladesch, Sri Lanka, Nepal, China, Japan, Südkorea, Nordkorea, Mongolei, Vietnam,
Thailand, Myanmar, Laos, Kambodscha, Malaysia, Indonesien, Philippinen, Singapur, Ägypten, Libyen, Tunesien, Algerien,
Marokko, Sudan, Südsudan, Äthiopien, Eritrea, Somalia, Dschibuti, Kenia, Uganda, Tansania, Ruanda, Burundi, Kongo,
Nigeria, Ghana, Kamerun, Senegal, Mali, Niger, Tschad, Guinea, Sierra Leone, Liberia, Togo, Benin, Burkina Faso,
Elfenbeinküste, Angola, Sambia, Simbabwe, Mosambik, Südafrika, Namibia, Madagaskar, USA, Kanada, Mexiko, Kuba,
Kolumbien, Venezuela, Ecuador, Peru, Bolivien, Chile, Argentinien, Brasilien, Paraguay, Uruguay, Australien, Neuseeland,
Germany, Austria, Switzerland, Ukraine, Russia, Turkey, Iran, Iraq, Syria, Poland, Romania, Bulgaria, Greece, Spain,
Italy, France, Netherlands, Belgium, Sweden, Norway, Denmark, Finland, Ireland, United Kingdom, United States,
Brazil, Colombia, Nigeria, Egypt, Morocco, Algeria, Tunisia, Ethiopia, Eritrea, Afghanistan, Pakistan, India, China
"""

_REGIONS = """
Baden-Württemberg, Bayern, Berlin, Brandenburg, Bremen, Hamburg, Hessen, Mecklenburg-Vorpommern, Niedersachsen,
Nordrhein-Westfalen, Rheinland-Pfalz, Saarland, Sachsen, Sachsen-Anhalt, Schleswig-Holstein, Thüringen, Franken,
Oberbayern, Niederbayern, Schwaben, Oberpfalz, Mittelfranken, Oberfranken, Unterfranken, Krim, Donbass, Galizien,
Transkarpatien, Siebenbürgen, Kurdistan, Katalonien, Lombardei, Anatolien
"""

_CITIES = """
München, Köln, Frankfurt, Stuttgart, Düsseldorf, Dortmund, Leipzig, Dresden, Hannover, Nürnberg, Duisburg, Bochum,
Wuppertal, Bielefeld, Bonn, Münster, Karlsruhe, Mannheim, Augsburg, Wiesbaden, Gelsenkirchen, Mönchengladbach,
Braunschweig, Chemnitz, Kiel, Aachen, Magdeburg, Freiburg, Krefeld, Lübeck, Oberhausen, Erfurt, Mainz, Rostock, Kassel,
Hagen, Hamm, Saarbrücken, Mülheim, Potsdam, Ludwigshafen, Oldenburg, Leverkusen, Osnabrück, Solingen, Heidelberg,
Herne, Neuss, Darmstadt, Paderborn, Regensburg, Ingolstadt, Würzburg, Fürth, Wolfsburg, Offenbach, Ulm, Heilbronn,
Pforzheim, Göttingen, Bottrop, Trier, Recklinghausen, Reutlingen, Koblenz, Bergisch Gladbach, Jena, Remscheid, Erlangen,
Moers, Siegen, Hildesheim, Salzgitter, Cottbus, Gera, Zwickau, Schwerin, Weimar, Flensburg, Konstanz, Bamberg, Bayreuth,
Landshut, Passau, Rosenheim, Kempten, Memmingen, Schweinfurt, Aschaffenburg, Amberg, Coburg, Straubing, Freising,
Dachau, Fürstenfeldbruck, Starnberg, Garching, Gräfelfing, Frechen, Pulheim, Hürth, Bergheim, Brühl, Troisdorf,
Wien, Graz, Linz, Salzburg, Innsbruck, Klagenfurt, Zürich, Bern, Basel, Genf, Lausanne, Luzern,
Paris, Lyon, Marseille, Toulouse, Nizza, Straßburg, Brüssel, Antwerpen, Amsterdam, Rotterdam, Den Haag, Utrecht,
Rom, Mailand, Neapel, Turin, Florenz, Venedig, Bologna, Padua, Genua, Palermo, Madrid, Barcelona, Valencia, Sevilla,
Lissabon, Porto, Athen, Thessaloniki, London, Manchester, Liverpool, Birmingham, Edinburgh, Glasgow, Dublin,
Kopenhagen, Stockholm, Oslo, Helsinki, Reykjavik, Warschau, Krakau, Breslau, Danzig, Posen, Lodz, Lublin, Prag, Brünn,
Bratislava, Pressburg, Budapest, Bukarest, Sofia, Belgrad, Zagreb, Ljubljana, Sarajevo, Skopje, Tirana, Pristina,
Chisinau, Riga, Vilnius, Tallinn, Minsk, Gomel, Grodno, Brest, Witebsk, Mogilew,
Kiew, Kyjiw, Kyiv, Charkiw, Charkow, Kharkiv, Odessa, Odesa, Dnipro, Dnipropetrowsk, Saporischschja, Saporischja, Saporoschje,
Lwiw, Lemberg, Lviv, Mariupol, Donezk, Donetsk, Luhansk, Lugansk, Cherson, Kherson, Mykolajiw, Nikolajew, Mykolaiv,
Poltawa, Poltava, Winnyzja, Winniza, Vinnytsia, Tschernihiw, Tschernigow, Sumy, Schytomyr, Shytomyr, Zhytomyr, Riwne,
Rowno, Luzk, Lutsk, Ternopil, Tarnopol, Iwano-Frankiwsk, Tscherkassy, Tscherkasy, Kropywnyzkyj, Krementschuk, Uschhorod,
Uzhhorod, Czernowitz, Tschernowzy, Chernivtsi, Melitopol, Berdjansk, Kramatorsk, Slowjansk, Bachmut, Sewastopol,
Simferopol, Jalta, Kertsch, Bila Zerkwa, Irpin, Butscha, Browary, Kamjanske, Krywyj Rih, Kriwoi Rog, Nikopol, Konotop,
Moskau, Sankt Petersburg, Petersburg, Nowosibirsk, Jekaterinburg, Kasan, Nischni Nowgorod, Samara, Omsk, Rostow, Ufa,
Krasnodar, Woronesch, Wolgograd, Perm, Krasnojarsk, Saratow, Tjumen, Kursk, Brjansk, Belgorod, Smolensk, Tula, Rjasan,
Istanbul, Ankara, Izmir, Bursa, Antalya, Adana, Konya, Gaziantep, Kayseri, Trabzon, Teheran, Isfahan, Schiras, Täbris,
Maschhad, Ahwaz, Rascht, Guilan, Bagdad, Basra, Mosul, Erbil, Damaskus, Aleppo, Homs, Latakia, Idlib, Beirut, Amman,
Jerusalem, Tel Aviv, Haifa, Gaza, Riad, Dschidda, Doha, Dubai, Abu Dhabi, Kuwait-Stadt, Maskat, Sanaa,
Kabul, Herat, Mazar-i-Sharif, Kandahar, Islamabad, Karatschi, Lahore, Peschawar, Delhi, Mumbai, Bombay, Kalkutta, Chennai,
Bangalore, Hyderabad, Pune, Dhaka, Kathmandu, Colombo, Peking, Beijing, Schanghai, Shanghai, Guangzhou, Shenzhen, Hongkong,
Tokio, Osaka, Seoul, Hanoi, Ho-Chi-Minh-Stadt, Saigon, Bangkok, Manila, Jakarta, Kuala Lumpur, Singapur,
Kairo, Alexandria, Tripolis, Tunis, Algier, Casablanca, Rabat, Marrakesch, Khartum, Addis Abeba, Asmara, Mogadischu,
Nairobi, Kampala, Daressalam, Kigali, Kinshasa, Lagos, Abuja, Kano, Ibadan, Benin City, Port Harcourt, Accra, Kumasi,
Dakar, Bamako, Conakry, Freetown, Monrovia, Abidjan, Douala, Jaunde, Luanda, Lusaka, Harare, Maputo, Kapstadt, Johannesburg,
Tiflis, Tbilisi, Eriwan, Jerewan, Baku, Almaty, Astana, Taschkent, Samarkand, Bischkek,
New York, Los Angeles, Chicago, Houston, Miami, Washington, San Francisco, Toronto, Montreal, Vancouver, Mexiko-Stadt,
Havanna, Bogotá, Medellín, Caracas, Quito, Lima, La Paz, Santiago, Buenos Aires, São Paulo, Rio de Janeiro, Montevideo,
Sydney, Melbourne, Auckland
"""


def _entries(blob):
    out = []
    for part in re.split(r"[,\n]", blob):
        part = part.strip()
        if part:
            out.append(part)
    return out


PLACES = sorted(set(_entries(_COUNTRIES) + _entries(_REGIONS) + _entries(_CITIES)), key=len, reverse=True)
PLACE_SET = set(PLACES)
RX_PLACES = re.compile(r"(?<![\w-])(?:%s)(?![\w])" % "|".join(re.escape(p) for p in PLACES))
# Dieselben Orte in Versalien (z. B. Überschriften in online erstellten Lebensläufen: "MÜNCHEN")
RX_PLACES_UPPER = re.compile(r"(?<![\w-])(?:%s)(?![\w])" % "|".join(re.escape(p.upper()) for p in PLACES if len(p) >= 4))
