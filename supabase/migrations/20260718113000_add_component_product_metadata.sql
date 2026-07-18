-- Add sourced product imagery and actionable reference/purchase links without
-- storing image binaries in the database. ResearchPanel already treats an
-- HTTP thumbnail value as a remote catalogue image and falls back to an icon.

update public.components as component
set
    thumbnail = metadata.thumbnail,
    datasheet_url = metadata.datasheet_url,
    buy_links = metadata.buy_links
from (
    values
        (
            'esp32-devkit-v1',
            'https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitc/_images/esp32-devkitc-v4-functional-overview.png',
            'https://www.espressif.com/sites/default/files/documentation/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.pdf',
            '[{"vendor":"Mouser","sku":"356-ESP32-DEVKITC32E","url":"https://www.mouser.in/en/ProductDetail/Espressif-Systems/ESP32-DevKitC-32E"}]'::jsonb
        ),
        (
            'ssd1306-oled',
            'https://cdn-shop.adafruit.com/480x360/326-04.jpg',
            'https://cdn-shop.adafruit.com/datasheets/SSD1306.pdf',
            '[{"vendor":"Adafruit","sku":"326","url":"https://www.adafruit.com/product/326"},{"vendor":"Mouser","sku":"485-326","url":"https://www.mouser.in/ProductDetail/Adafruit/326"}]'::jsonb
        ),
        (
            'dht22-sensor',
            'https://cdn-shop.adafruit.com/480x360/385-00.jpg',
            'https://cdn-shop.adafruit.com/datasheets/Digital%20humidity%20and%20temperature%20sensor%20AM2302.pdf',
            '[{"vendor":"Adafruit reference","sku":"385","url":"https://www.adafruit.com/product/385"},{"vendor":"DigiKey search","url":"https://www.digikey.in/en/products?keywords=DHT22"}]'::jsonb
        ),
        (
            'bme280-sensor',
            'https://cdn-shop.adafruit.com/480x360/2652-04.jpg',
            'https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bme280-ds002.pdf',
            '[{"vendor":"Adafruit","sku":"2652","url":"https://www.adafruit.com/product/2652"},{"vendor":"DigiKey","sku":"1528-2652-ND","url":"https://www.digikey.in/en/products/detail/adafruit-industries-llc/2652/5604372"}]'::jsonb
        ),
        (
            'mpu6050-imu',
            'https://cdn-shop.adafruit.com/480x360/3886-05.jpg',
            'https://product.tdk.com/system/files/dam/doc/product/sensor/mortion-inertial/imu/data_sheet/mpu-6000-datasheet1.pdf',
            '[{"vendor":"Adafruit","sku":"3886","url":"https://www.adafruit.com/product/3886"}]'::jsonb
        ),
        (
            'servo-motor',
            'https://cdn-shop.adafruit.com/480x360/169-06.jpg',
            'https://cdn-shop.adafruit.com/product-files/5592/C17481_SG92R_datasheet.pdf',
            '[{"vendor":"Adafruit","sku":"169","url":"https://www.adafruit.com/product/169"}]'::jsonb
        )
) as metadata(slug, thumbnail, datasheet_url, buy_links)
where component.slug = metadata.slug;
