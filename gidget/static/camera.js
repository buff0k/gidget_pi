const canvas =
    document.getElementById(
        "cameraOverlay"
    );

const image =
    document.getElementById(
        "cameraFeed"
    );


const ctx =
    canvas.getContext("2d");


function resizeCanvas()
{
    canvas.width =
        image.clientWidth;

    canvas.height =
        image.clientHeight;
}


image.onload = resizeCanvas;

window.onresize =
    resizeCanvas;


async function loadState()
{

    const response =
        await fetch(
            "/camera/api/state"
        );

    return await response.json();

}


async function loadSensors()
{

    let lidar = {};
    let imu = {};
    let env = {};


    try {

        lidar =
            await (
                await fetch(
                    "/lidar/api/state"
                )
            ).json();

    } catch(e){}


    try {

        imu =
            await (
                await fetch(
                    "/imu/api/state"
                )
            ).json();

    } catch(e){}


    try {

        env =
            await (
                await fetch(
                    "/api/status"
                )
            ).json();

    } catch(e){}


    return {
        lidar,
        imu,
        env
    };

}


async function drawOverlay()
{

    ctx.clearRect(
        0,
        0,
        canvas.width,
        canvas.height
    );


    const data =
        await loadSensors();


    ctx.font =
        "22px monospace";


    ctx.fillStyle =
        "white";


    let y = 35;


    if (
        document.getElementById(
            "lidarToggle"
        ).checked
    )
    {

        ctx.fillText(
            "LIDAR: " +
            (
                data.lidar.distance ||
                "n/a"
            ),
            20,
            y
        );

        y += 30;

    }


    if (
        document.getElementById(
            "imuToggle"
        ).checked
    )
    {

        ctx.fillText(
            "IMU: " +
            (
                data.imu.pitch ||
                "n/a"
            ),
            20,
            y
        );

        y += 30;

    }


    if (
        document.getElementById(
            "environmentToggle"
        ).checked
    )
    {

        ctx.fillText(
            "Climate: " +
            (
                data.env.temperature ||
                "n/a"
            ),
            20,
            y
        );

    }

}


setInterval(
    drawOverlay,
    1000
);