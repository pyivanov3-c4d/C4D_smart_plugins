CONTAINER Osplinetensor
{
    NAME Osplinetensor;
    INCLUDE Obase;
    GROUP ID_OBJECTPROPERTIES
    {
        BOOL ST_CLOSED { DEFAULT 1; }
        REAL ST_WIDTH { UNIT METER; MIN 0.0; STEP 1.0; }
        LONG ST_SUBDIVISION { MIN 0; MAX 64; STEP 1; }
        LONG ST_DENSITY { MIN 1; STEP 1; DEFAULT 1; }
        SPLINE ST_CURVE { }
    }
}
