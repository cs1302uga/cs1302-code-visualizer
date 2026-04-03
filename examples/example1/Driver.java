public class Driver {

    public static void main(String[] args) {
        MealType meal = MealType.BREAKFAST;
        System.out.println(meal.hashCode());
    } // main

} // Driver

enum Day {
    SUNDAY, MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY;
} // Day

enum MealType {
    BREAKFAST, LUNCH, DINNER;
} // MealType
