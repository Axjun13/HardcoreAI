-- Give Research mode enough real catalogue coverage to compare useful parts.
-- Library ids intentionally match backend/data/libraries.json so Phase 3 can
-- resolve documentation and materialize PlatformIO dependencies.

alter table public.components
    add column if not exists library_ids jsonb not null default '[]'::jsonb,
    add column if not exists buy_links jsonb not null default '[]'::jsonb,
    add column if not exists datasheet_url text,
    add column if not exists aliases jsonb not null default '[]'::jsonb;

insert into public.components
    (slug, name, library_name, library_ids, aliases, description, is_controller,
     category, visual_type, thumbnail, width, height)
values
    ('esp32-devkit-v1', 'ESP32 DevKit V1', null, '[]'::jsonb,
     '["esp32", "wifi", "bluetooth", "devkit"]'::jsonb,
     'Wi-Fi and Bluetooth development board for connected embedded products.',
     true, 'Microcontroller', 'board', 'board', 190, 260),
    ('ssd1306-oled', 'SSD1306 OLED Display', null,
     '["adafruit-ssd1306", "adafruit-gfx"]'::jsonb,
     '["oled", "i2c display", "128x64 display"]'::jsonb,
     'Compact monochrome I2C/SPI display for status, menus, and sensor readings.',
     false, 'Display', 'display', 'oled', 150, 100),
    ('dht22-sensor', 'DHT22 Temperature & Humidity Sensor', null,
     '["dht-sensor", "adafruit-sensor"]'::jsonb,
     '["am2302", "temperature", "humidity", "climate sensor"]'::jsonb,
     'Low-cost digital temperature and humidity sensor for slow environmental sampling.',
     false, 'Sensor', 'sensor', 'sensor', 130, 110),
    ('bme280-sensor', 'BME280 Environmental Sensor', null,
     '["adafruit-bme280", "adafruit-sensor"]'::jsonb,
     '["pressure", "temperature", "humidity", "weather sensor"]'::jsonb,
     'I2C/SPI temperature, humidity, and barometric pressure sensor for weather and altitude projects.',
     false, 'Sensor', 'sensor', 'sensor', 140, 105),
    ('mpu6050-imu', 'MPU6050 6-Axis IMU', null,
     '["adafruit-mpu6050", "adafruit-sensor"]'::jsonb,
     '["imu", "accelerometer", "gyroscope", "motion sensor"]'::jsonb,
     'I2C accelerometer and gyroscope module for motion, tilt, and vibration measurement.',
     false, 'Sensor', 'sensor', 'sensor', 140, 110),
    ('servo-motor', 'Hobby Servo Motor', null, '["servo"]'::jsonb,
     '["sg90", "servo", "position motor"]'::jsonb,
     'PWM-positioned hobby actuator; choose torque and supply current for the mechanical load.',
     false, 'Actuator', 'motor', 'motor', 150, 110)
on conflict (slug) do update set
    name = excluded.name,
    library_name = excluded.library_name,
    library_ids = excluded.library_ids,
    aliases = excluded.aliases,
    description = excluded.description,
    is_controller = excluded.is_controller,
    category = excluded.category,
    visual_type = excluded.visual_type,
    thumbnail = excluded.thumbnail,
    width = excluded.width,
    height = excluded.height;

delete from public.pins
where component_id in (
    select id from public.components where slug in (
        'esp32-devkit-v1', 'ssd1306-oled', 'dht22-sensor',
        'bme280-sensor', 'mpu6050-imu', 'servo-motor'
    )
);

insert into public.pins (component_id, name, label, side, x, y, role, is_input, is_output)
select id, '3V3', '3V3', 'left', 0, 30, 'vcc', false, true from public.components where slug = 'esp32-devkit-v1'
union all select id, 'GND', 'GND', 'left', 0, 55, 'gnd', true, false from public.components where slug = 'esp32-devkit-v1'
union all select id, 'GPIO21', 'GPIO21 / SDA', 'right', 190, 45, 'i2c-sda', true, true from public.components where slug = 'esp32-devkit-v1'
union all select id, 'GPIO22', 'GPIO22 / SCL', 'right', 190, 70, 'i2c-scl', true, true from public.components where slug = 'esp32-devkit-v1'
union all select id, 'GPIO18', 'GPIO18 / SCK', 'right', 190, 95, 'spi-sck', true, true from public.components where slug = 'esp32-devkit-v1'
union all select id, 'GPIO23', 'GPIO23 / MOSI', 'right', 190, 120, 'spi-mosi', true, true from public.components where slug = 'esp32-devkit-v1'
union all select id, 'GPIO19', 'GPIO19 / MISO', 'right', 190, 145, 'spi-miso', true, true from public.components where slug = 'esp32-devkit-v1'
union all select id, 'VCC', 'VCC', 'left', 0, 20, 'vcc', true, false from public.components where slug = 'ssd1306-oled'
union all select id, 'GND', 'GND', 'left', 0, 40, 'gnd', true, false from public.components where slug = 'ssd1306-oled'
union all select id, 'SCL', 'SCL', 'right', 150, 35, 'i2c-scl', true, false from public.components where slug = 'ssd1306-oled'
union all select id, 'SDA', 'SDA', 'right', 150, 60, 'i2c-sda', true, true from public.components where slug = 'ssd1306-oled'
union all select id, 'VCC', 'VCC', 'left', 0, 25, 'vcc', true, false from public.components where slug = 'dht22-sensor'
union all select id, 'DATA', 'DATA', 'right', 130, 45, 'digital-data', true, true from public.components where slug = 'dht22-sensor'
union all select id, 'GND', 'GND', 'left', 0, 75, 'gnd', true, false from public.components where slug = 'dht22-sensor'
union all select id, 'VCC', 'VCC', 'left', 0, 20, 'vcc', true, false from public.components where slug = 'bme280-sensor'
union all select id, 'GND', 'GND', 'left', 0, 45, 'gnd', true, false from public.components where slug = 'bme280-sensor'
union all select id, 'SCL', 'SCL / SCK', 'right', 140, 35, 'i2c-scl', true, false from public.components where slug = 'bme280-sensor'
union all select id, 'SDA', 'SDA / SDI', 'right', 140, 65, 'i2c-sda', true, true from public.components where slug = 'bme280-sensor'
union all select id, 'VCC', 'VCC', 'left', 0, 20, 'vcc', true, false from public.components where slug = 'mpu6050-imu'
union all select id, 'GND', 'GND', 'left', 0, 45, 'gnd', true, false from public.components where slug = 'mpu6050-imu'
union all select id, 'SCL', 'SCL', 'right', 140, 35, 'i2c-scl', true, false from public.components where slug = 'mpu6050-imu'
union all select id, 'SDA', 'SDA', 'right', 140, 65, 'i2c-sda', true, true from public.components where slug = 'mpu6050-imu'
union all select id, 'VCC', 'VCC', 'left', 0, 25, 'vcc', true, false from public.components where slug = 'servo-motor'
union all select id, 'PWM', 'PWM', 'right', 150, 50, 'pwm', true, false from public.components where slug = 'servo-motor'
union all select id, 'GND', 'GND', 'left', 0, 78, 'gnd', true, false from public.components where slug = 'servo-motor';
