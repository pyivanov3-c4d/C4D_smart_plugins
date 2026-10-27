CONTAINER Ochamferpro
{
    NAME Ochamferpro;
    INCLUDE Obase;
    GROUP ID_OBJECTPROPERTIES
    {
        REAL CP_ANGLE { UNIT DEGREE; MIN 0; MAX 180; STEP 1; }
        REAL CP_RADIUS { UNIT METER; MIN 0; STEP 0.1; }
        SEPARATOR {}
        STATICTEXT CP_STATUS {}
    }
}
